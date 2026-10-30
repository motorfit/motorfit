"""Serial RobStride CAN transactions: one request, then its addressed reply.

Control/write/enable/disable ordering follows RobStride/Python_Sample at
cbf977e56c842d57a65f3f17c1b1ecaef002c424 (bus.py and operation_control.py).
Idle type-2 polling follows MagicBox Get_Motor_State(). Model field ranges
follow each pinned official manual, not the conflicting Python sample table.
This single-owner transport must not be shared between concurrent callers.
"""

import math
import struct
import time

import can

from .models import MotorSpec
from .protocol import Feedback, _matches, _message, decode_feedback, encode_command


class Motor:
    def __init__(
        self,
        spec: MotorSpec,
        channel="can0",
        motor_id=127,
        host_id=255,
        timeout=0.2,
        on_frame=None,
    ):
        struct.pack("BB", motor_id, host_id)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("CAN timeout must be positive and finite")
        self.spec = spec
        self.motor_id = motor_id
        self.host_id = host_id
        self.timeout = timeout
        self.on_frame = on_frame
        self.discarded_frames = 0
        self.bus = can.Bus(interface="socketcan", channel=channel)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        cleanup_error = None
        for cleanup in (self.stop, self.close):
            try:
                cleanup()
            except Exception as error:
                if exc_value is not None:
                    exc_value.add_note(f"{cleanup.__name__} failed: {error}")
                elif cleanup_error is None:
                    cleanup_error = error
        if cleanup_error is not None:
            raise cleanup_error

    def _send(self, message):
        self.bus.send(message, timeout=self.timeout)
        if self.on_frame is not None:
            self.on_frame("tx", message)

    def _recv(self, timeout):
        message = self.bus.recv(timeout)
        if message is not None and self.on_frame is not None:
            self.on_frame("rx", message)
        return message

    def _request(self, kind, data=bytes(8)):
        self._send(_message(kind, self.motor_id, self.host_id, data))

    def _raise_fault(self, message):
        if not _matches(message, self.motor_id, self.host_id):
            return
        if message.arbitration_id >> 24 == 21:
            fault, warning = struct.unpack("<II", message.data)
            if fault:
                raise RuntimeError(
                    f"{self.spec.name} device fault 0x{fault:08x} (warning 0x{warning:08x})"
                )
        feedback = decode_feedback(
            message, spec=self.spec, motor_id=self.motor_id, host_id=self.host_id
        )
        if feedback is not None and feedback.faults:
            raise RuntimeError(f"{self.spec.name} device faults: 0x{feedback.faults:x}")

    def _discard_pending(self, *, stopping=False):
        """Log queued old frames before sending; none can acknowledge a new request."""
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            message = self._recv(0.0)
            if message is None:
                return
            self.discarded_frames += 1
            if not stopping:
                self._raise_fault(message)
        raise TimeoutError(f"{self.spec.name} receive queue did not drain before request")

    def _wait_status(self, operation, *, expected_mode=None) -> Feedback:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            message = self._recv(max(0.0, deadline - time.monotonic()))
            if message is None:
                break
            self._raise_fault(message)
            feedback = decode_feedback(
                message, spec=self.spec, motor_id=self.motor_id, host_id=self.host_id
            )
            if feedback is None:
                continue
            if expected_mode is not None and feedback.mode != expected_mode:
                raise RuntimeError(
                    f"{self.spec.name} {operation} replied in mode {feedback.mode}; "
                    f"expected mode {expected_mode}"
                )
            return feedback
        raise TimeoutError(f"No {self.spec.name} type-2 reply for {operation}")

    def _status_transaction(self, kind, data=bytes(8), *, operation, expected_mode=None):
        self._discard_pending()
        self._request(kind, data)
        return self._wait_status(operation, expected_mode=expected_mode)

    def prepare(self) -> Feedback:
        """Stop and disable periodic reports once, before acquisition begins."""
        self.stop()
        return self._status_transaction(
            24,
            bytes((1, 2, 3, 4, 5, 6, 0, 0)),
            operation="disable periodic reports",
            expected_mode=0,
        )

    def _write_verified(self, index, value, format):
        payload = struct.pack("<H2x", index) + struct.pack("<" + format, value).ljust(4, b"\0")
        self._status_transaction(
            18, payload, operation=f"write register 0x{index:04x}", expected_mode=0
        )
        actual = self.read_parameter(index, format)
        if actual != value:
            raise RuntimeError(
                f"{self.spec.name} register 0x{index:04x} readback {actual!r}; expected {value!r}"
            )

    def start(self, watchdog_ms=100) -> Feedback:
        """Verify each configuration write before enabling MIT mode.

        The manual defines 20000 canTimeout ticks per second. Readbacks are
        initialization-only; no register queries are interleaved with control.
        """
        if not math.isfinite(watchdog_ms) or not 0 < round(watchdog_ms * 20) <= 0xFFFFFFFF:
            raise ValueError("watchdog_ms must encode a positive uint32 timeout")
        self.prepare()
        self._write_verified(0x7005, 0, "B")
        self._write_verified(0x7028, round(watchdog_ms * 20), "I")
        return self._status_transaction(3, operation="enable", expected_mode=2)

    def command(self, position, velocity, kp, kd, torque) -> Feedback:
        """Send one type-1 command and consume its type-2 reply before returning."""
        message = encode_command(
            position, velocity, kp, kd, torque, spec=self.spec, motor_id=self.motor_id
        )
        self._discard_pending()
        self._send(message)
        return self._wait_status("motion command", expected_mode=2)

    def read_parameter(self, index: int, format: str = "f") -> float | int:
        """Read a scalar in a separate transaction, outside the control loop."""
        if format not in {"f", "B", "H", "I", "h", "i"}:
            raise ValueError(f"Unsupported register format: {format!r}")
        payload = struct.pack("<H6x", index)
        self._discard_pending()
        self._request(17, payload)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            message = self._recv(max(0.0, deadline - time.monotonic()))
            if message is None:
                break
            self._raise_fault(message)
            if not _matches(message, self.motor_id, self.host_id):
                continue
            if message.arbitration_id >> 24 != 17 or message.data[:2] != payload[:2]:
                continue
            if (message.arbitration_id >> 16) & 0xFF:
                raise RuntimeError(f"{self.spec.name} rejected register read 0x{index:04x}")
            value = struct.unpack_from("<" + format, message.data, 4)[0]
            if not math.isfinite(value):
                raise RuntimeError(f"{self.spec.name} register 0x{index:04x} is not finite")
            return value
        raise TimeoutError(f"No {self.spec.name} register 0x{index:04x} reply")

    def read_position(self) -> float:
        """Use the same type-2 position coordinate as control and acquisition."""
        return self.read_state().position

    def read_state(self) -> Feedback:
        """Poll type 2 as MagicBox Get_Motor_State does; reserved bytes are zero."""
        return self._status_transaction(2, operation="state request")

    def stop(self) -> Feedback:
        # A stale frame/logging/drain error must never prevent the stop command.
        try:
            self._discard_pending(stopping=True)
        finally:
            self._request(4)
        return self._wait_status("stop", expected_mode=0)

    def close(self):
        self.bus.shutdown()

"""Single-owner Damiao SocketCAN transactions with fresh addressed responses.

Register writes affect RAM only: this adapter never sends save, clear-error
or hardware-zero commands.
"""

import math
import struct
import time

import can

from .protocol import addressed, decode_feedback, encode_command, message


class Motor:
    def __init__(self, spec, channel="can0", motor_id=1, host_id=17, timeout=0.2, on_frame=None):
        if spec.family != "damiao":
            raise ValueError("Damiao driver requires a Damiao motor specification")
        if not 1 <= motor_id <= 0x7FE or not 0 <= host_id <= 0x7FF:
            raise ValueError("Expected motor_id=1..2046 and feedback_id=0..2047")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("CAN timeout must be positive and finite")
        self.spec, self.motor_id, self.feedback_id = spec, motor_id, host_id
        self.timeout, self.on_frame = timeout, on_frame
        self.bus = can.Bus(interface="socketcan", channel=channel)

    def _send(self, frame):
        self.bus.send(frame, timeout=self.timeout)
        if self.on_frame:
            self.on_frame("tx", frame)

    def _recv(self, timeout):
        frame = self.bus.recv(timeout)
        if frame is not None and self.on_frame:
            self.on_frame("rx", frame)
        return frame

    def _drain(self):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self._recv(0) is None:
                return
        raise TimeoutError("Damiao receive queue did not drain")

    def _wait(self, operation, *, marker=None, rid=None, mode=None):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            frame = self._recv(max(0, deadline - time.monotonic()))
            if frame is None:
                break
            if not addressed(frame, self.feedback_id):
                continue
            if marker is not None and frame.data[:4] == struct.pack(
                "<HBB", self.motor_id, marker, rid
            ):
                return bytes(frame.data[4:])
            feedback = decode_feedback(
                frame, spec=self.spec, motor_id=self.motor_id, feedback_id=self.feedback_id
            )
            if feedback is None:
                continue
            if feedback.faults:
                raise RuntimeError(
                    f"{self.spec.name} Damiao status fault 0x{feedback.status_code:x}"
                )
            if marker is None:
                if mode is not None and feedback.mode != mode:
                    raise RuntimeError(
                        f"{self.spec.name} mode {feedback.mode}; expected mode {mode}"
                    )
                return feedback
        raise TimeoutError(f"No fresh {self.spec.name} reply for {operation}")

    def _status(self, frame, operation, mode=None):
        self._drain()
        self._send(frame)
        return self._wait(operation, mode=mode)

    def read_parameter(self, index, format="f"):
        if format not in {"f", "I"}:
            raise ValueError("Damiao registers are float32 or uint32")
        self._drain()
        self._send(message(0x7FF, struct.pack("<HBBI", self.motor_id, 0x33, index, 0)))
        raw = self._wait(f"register {index}", marker=0x33, rid=index)
        value = struct.unpack("<" + format, raw)[0]
        if not math.isfinite(value):
            raise RuntimeError(f"Nonfinite Damiao register {index}")
        return value

    def _write_verified(self, index, value):
        self._drain()
        self._send(message(0x7FF, struct.pack("<HBBI", self.motor_id, 0x55, index, value)))
        ack = self._wait(f"write register {index}", marker=0x55, rid=index)
        if struct.unpack("<I", ack)[0] != value or self.read_parameter(index, "I") != value:
            raise RuntimeError(f"Damiao register {index} write/readback mismatch")

    def prepare(self):
        self.stop()
        # Runtime mapping registers are authoritative. Reject mismatches instead
        # of silently changing PMAX/VMAX/TMAX on a mounted device.
        for index, name in ((21, "position"), (22, "velocity"), (23, "torque")):
            actual = self.read_parameter(index)
            low, high = getattr(self.spec, name)
            if not math.isclose(low, -high) or not math.isclose(actual, high, rel_tol=1e-6):
                raise ValueError(f"Damiao {name} range mismatch: device={actual}, profile={high}")

    def start(self, watchdog_ms=100):
        if not math.isfinite(watchdog_ms) or not 0 < round(watchdog_ms * 20) <= 0xFFFFFFFF:
            raise ValueError("watchdog_ms must encode a positive uint32 timeout")
        self.prepare()
        if self.read_parameter(10, "I") != 1:
            self._write_verified(10, 1)
        self._write_verified(9, round(watchdog_ms * 20))
        return self._status(message(self.motor_id, b"\xff" * 7 + b"\xfc"), "enable", mode=2)

    def command(self, position, velocity, kp, kd, torque):
        return self._status(
            encode_command(
                position, velocity, kp, kd, torque, spec=self.spec, motor_id=self.motor_id
            ),
            "MIT command",
            mode=2,
        )

    def read_state(self):
        return self._status(
            message(0x7FF, struct.pack("<HBBI", self.motor_id, 0xCC, 0, 0)), "state request"
        )

    def read_position(self):
        return self.read_state().position

    def stop(self):
        try:
            self._drain()
        finally:
            self._send(message(self.motor_id, b"\xff" * 7 + b"\xfd"))
        return self._wait("disable", mode=0)

    def close(self):
        self.bus.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        try:
            self.stop()
        except Exception as cleanup:
            if error is None:
                raise
            error.add_note(f"Motor disable failed: {cleanup}")
        finally:
            self.close()

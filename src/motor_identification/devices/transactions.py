"""Single-owner SocketCAN transactions shared by native effort drivers."""

import math
import time
from dataclasses import dataclass

import can


@dataclass(frozen=True)
class State:
    position: float
    velocity: float
    torque: float
    timestamp: float
    arbitration_id: int
    mode: int = -1  # -1 means the protocol does not report enable state.
    faults: int = -1  # -1 means this reply has no fault field.
    temperature: float | None = None
    current: float | None = None
    statusword: int | None = None


def message(identifier, data, *, extended=False):
    return can.Message(arbitration_id=identifier, data=data, is_extended_id=extended, check=True)


def addressed(frame, identifier, *, extended=False, length=8):
    return (
        frame.arbitration_id == identifier
        and frame.is_extended_id == extended
        and not frame.is_error_frame
        and not frame.is_remote_frame
        and frame.dlc == length
        and len(frame.data) == length
    )


def integer(value, scale, low, high):
    if not math.isfinite(value):
        raise ValueError("Command must be finite")
    raw = round(value / scale)
    if not low <= raw <= high:
        raise ValueError("Command exceeds protocol representation")
    return raw


class SocketMotor:
    family = ""
    fd = False

    def __init__(self, spec, channel="can0", motor_id=1, host_id=None, timeout=0.2, on_frame=None):
        if spec.family != self.family:
            raise ValueError(f"Expected a {self.family} motor specification")
        if not isinstance(motor_id, int) or not 1 <= motor_id <= 127:
            raise ValueError("Expected motor_id=1..127")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("CAN timeout must be positive and finite")
        self.spec, self.motor_id, self.timeout = spec, motor_id, timeout
        self.on_frame, self.active = on_frame, False
        self.validate_feedback_id(host_id)
        self.info = {"family": self.family}
        self.bus = can.Bus(interface="socketcan", channel=channel, fd=self.fd)

    def validate_feedback_id(self, identifier):
        raise NotImplementedError

    def send(self, frame):
        self.bus.send(frame, timeout=self.timeout)
        if self.on_frame:
            self.on_frame("tx", frame)

    def recv(self, timeout):
        frame = self.bus.recv(timeout)
        if frame is not None and self.on_frame:
            self.on_frame("rx", frame)
        return frame

    def drain(self):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.recv(0) is None:
                return
        raise TimeoutError("Receive queue did not drain")

    def exchange(self, request, match, *, ensure_send=False):
        try:
            self.drain()
        except BaseException:
            if ensure_send:
                self.send(request)
            raise
        self.send(request)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            frame = self.recv(max(0, deadline - time.monotonic()))
            if frame is None:
                break
            if match(frame):
                return frame
        raise TimeoutError(f"No fresh {self.family} reply to {bytes(request.data).hex()}")

    def check_torque(self, torque):
        if not math.isfinite(torque) or not self.spec.torque[0] <= torque <= self.spec.torque[1]:
            raise ValueError("Torque outside configured experiment limits")

    def read_position(self):
        return self.read_state().position

    def prepare(self):
        self.stop()

    def close(self):
        self.bus.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        try:
            if self.active:
                self.stop()
        except Exception as cleanup:
            if error is None:
                raise
            error.add_note(f"Motor disable failed: {cleanup}")
        finally:
            self.close()

"""Independent ht_can pure-torque commands and addressed sensor requests."""

import math
import struct

from ..transactions import SocketMotor, State, addressed, integer, message


class Motor(SocketMotor):
    family = "hightorque"

    def validate_feedback_id(self, identifier):
        self.feedback_id = self.motor_id if identifier is None else identifier
        if not isinstance(self.feedback_id, int) or not 0 <= self.feedback_id <= 0x1FFFFFFF:
            raise ValueError("Invalid HighTorque feedback_id")

    def frame(self, data):
        return message(0x8000 | self.motor_id, data, extended=True)

    def start(self, watchdog_ms=0):
        if watchdog_ms != 0:
            raise ValueError(
                "ht_can has no implemented watchdog write: set watchdog_ms=0 "
                "and configure/verify the drive timeout externally"
            )
        self.prepare()
        self.info.update(
            watchdog="external; not configured or verified by MotorFit",
            enable_state="commanded; absent from sensor reply",
        )
        self.active = True
        self.command_torque(0.0)

    def command_torque(self, torque):
        if not self.active:
            raise RuntimeError("Start torque mode before commanding torque")
        self.check_torque(torque)
        raw = integer(torque, 0.01, -32767, 32767)  # -32768 is an unset sentinel.
        raw = max(
            math.ceil(self.spec.torque[0] * 100), min(math.floor(self.spec.torque[1] * 100), raw)
        )
        self.send(self.frame(b"\x05\x13" + struct.pack("<h", raw)))
        return raw * 0.01

    def read_state(self):
        def matches(f):
            # The response address/layout is configured explicitly; don't mask
            # arbitrary CAN IDs down to seven bits and accept unrelated traffic.
            valid = addressed(f, self.feedback_id, extended=True)
            if self.feedback_id <= 0x7FF:
                valid = valid or addressed(f, self.feedback_id)
            return valid and f.data[:2] == b"\x27\x01"

        reply = self.exchange(self.frame(b"\x17\x01" + bytes(6)), matches)
        p, v, t = struct.unpack_from("<hhh", reply.data, 2)
        if -32768 in (p, v, t):
            raise RuntimeError("HighTorque returned an unavailable sensor value")
        return State(
            position=p * 0.0001 * math.tau,
            velocity=v * 0.00025 * math.tau,
            torque=t * 0.01,
            timestamp=reply.timestamp,
            arbitration_id=reply.arbitration_id,
        )

    def inspect(self):
        return {
            "feedback_id": self.feedback_id,
            "status": "Position, speed and torque only; no enable/fault/temperature fields",
        }

    def stop(self):
        # No stop acknowledgement exists in this protocol.
        self.send(self.frame(b"\x01\x00\x00"))
        self.active = False

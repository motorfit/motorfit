"""Independent RMD-X V3 current-control driver (0x140/0x240 CAN IDs)."""

import math
import struct

from ..transactions import SocketMotor, State, addressed, integer, message


class Motor(SocketMotor):
    family = "myactuator"

    def validate_feedback_id(self, identifier):
        self.feedback_id = 0x240 + self.motor_id
        if identifier is not None and identifier != self.feedback_id:
            raise ValueError("RMD-X V3 feedback_id must be 0x240 + motor_id")

    def request(self, command, payload=bytes(7)):
        return self.exchange(
            message(0x140 + self.motor_id, bytes([command]) + payload),
            lambda f: addressed(f, self.feedback_id) and f.data[0] == command,
            ensure_send=command == 0x80,
        )

    def start(self, watchdog_ms=100):
        watchdog = integer(watchdog_ms, 1, 1, 0xFFFFFFFF)
        self.prepare()
        payload = bytes(3) + struct.pack("<I", watchdog)
        reply = self.request(0xB3, payload)
        if bytes(reply.data[1:]) != payload:
            raise RuntimeError("MyActuator watchdog echo mismatch")
        self.info.update(watchdog_ms=watchdog, watchdog_storage="device ROM (0xB3)")
        self.active = True  # Cleanup is required from the first enabling command.
        self.request(0x77)  # Brake release; no zeroing or fault clearing.
        self.command_torque(0.0)

    def command_torque(self, torque):
        if not self.active:
            raise RuntimeError("Start current mode before commanding torque")
        self.check_torque(torque)
        kt = self.spec.protocol["torque_constant_nm_per_a"]
        limit = self.spec.protocol["current_limit_a"]
        current = max(-limit, min(limit, torque / kt))
        raw = integer(current, 0.01, -32768, 32767)
        # Quantization must not round beyond a nonintegral current limit.
        raw = max(-math.floor(limit * 100), min(math.floor(limit * 100), raw))
        self.request(0xA1, bytes(3) + struct.pack("<h", raw) + bytes(2))
        return raw * 0.01 * kt

    def read_state(self):
        status = self.request(0x9C)
        angle = self.request(0x92)
        errors = self.request(0x9A)
        faults = struct.unpack_from("<H", errors.data, 6)[0]
        if faults:
            raise RuntimeError(f"MyActuator faults: 0x{faults:04x}")
        current = struct.unpack_from("<h", status.data, 2)[0] * 0.01
        return State(
            position=math.radians(struct.unpack_from("<i", angle.data, 4)[0] * 0.01),
            velocity=math.radians(struct.unpack_from("<h", status.data, 4)[0]),
            torque=current * self.spec.protocol["torque_constant_nm_per_a"],
            current=current,
            temperature=struct.unpack_from("b", status.data, 1)[0],
            faults=faults,
            timestamp=angle.timestamp,
            arbitration_id=angle.arbitration_id,
        )

    def inspect(self):
        return {
            "firmware_date": struct.unpack_from("<I", self.request(0xB2).data, 4)[0],
            "operating_mode": self.request(0x70).data[7],
        }

    def stop(self):
        self.request(0x80)
        self.active = False

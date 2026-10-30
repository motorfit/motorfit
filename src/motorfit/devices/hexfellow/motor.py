"""Independent CANopen/SocketCAN-FD effort acquisition for firmware 07 and 08.

Expedited SDOs keep each reply attributable. No PDO mapping or saved parameters
are changed. This intentionally trades sampling rate for a simple bench path.
"""

import math
import struct
import time

from ..transactions import SocketMotor, State, addressed, integer, message


class Motor(SocketMotor):
    family = "hexfellow"
    fd = True

    def validate_feedback_id(self, identifier):
        self.feedback_id = 0x580 + self.motor_id
        if identifier is not None and identifier != self.feedback_id:
            raise ValueError("Hexfellow feedback_id must be 0x580 + motor_id")
        self.master_id = 126 if self.motor_id != 126 else 125
        self.version = None
        self.peak_torque = None
        self.last_reply = None
        self.last_heartbeat = 0.0
        self.watchdog_ms = None

    def sdo(self, index, subindex=0, payload=None):
        prefix = struct.pack("<HB", index, subindex)
        if payload is None:
            command, tail = 0x40, bytes(4)
        else:
            command = {1: 0x2F, 2: 0x2B, 4: 0x23}[len(payload)]
            tail = payload.ljust(4, b"\x00")
        frame = self.exchange(
            message(0x600 + self.motor_id, bytes([command]) + prefix + tail),
            lambda f: addressed(f, self.feedback_id) and f.data[1:4] == prefix,
            ensure_send=index == 0x6040 and payload == bytes(2),
        )
        self.last_reply = frame
        if frame.data[0] == 0x80:
            abort = struct.unpack_from("<I", frame.data, 4)[0]
            raise RuntimeError(f"SDO abort 0x{abort:08x} at {index:04x}:{subindex:02x}")
        if payload is not None:
            if frame.data[0] != 0x60:
                raise RuntimeError("Unexpected SDO write response")
            return None
        sizes = {0x4F: 1, 0x4B: 2, 0x47: 3, 0x43: 4}
        if frame.data[0] not in sizes:
            raise RuntimeError("Expected an expedited, size-indicated SDO upload")
        return bytes(frame.data[4 : 4 + sizes[frame.data[0]]])

    def read(self, index, fmt, subindex=0):
        raw = self.sdo(index, subindex)
        if len(raw) != struct.calcsize("<" + fmt):
            raise RuntimeError(f"SDO size mismatch at {index:04x}:{subindex:02x}")
        value = struct.unpack("<" + fmt, raw)[0]
        if not math.isfinite(value):
            raise RuntimeError("Nonfinite SDO value")
        return value

    def write(self, index, fmt, value, subindex=0, verify=False):
        self.sdo(index, subindex, struct.pack("<" + fmt, value))
        if verify and self.read(index, fmt, subindex) != value:
            raise RuntimeError(f"SDO readback mismatch at {index:04x}:{subindex:02x}")

    def identify(self):
        if self.version is not None:
            return
        version = self.read(0x1018, "I", 3)
        if version != self.spec.protocol["firmware_version"]:
            raise ValueError(f"Hexfellow firmware {version} differs from configured revision")
        peak = self.read(0x6076, "I" if version == 7 else "f")
        if version == 7:
            peak *= 0.001  # Firmware 07: uint32 mNm; 08: float32 Nm.
        if peak <= 0 or max(abs(v) for v in self.spec.torque) > peak:
            raise ValueError("Experiment torque limits exceed reported Hexfellow peak torque")
        self.version, self.peak_torque = version, peak
        self.info.update(
            firmware_version=version,
            peak_torque_nm=peak,
            position_encoding="Q21 rev" if version == 7 else "float32 rev",
        )

    def heartbeat(self, force=False):
        now = time.monotonic()
        if force or now - self.last_heartbeat >= self.watchdog_ms / 3000:
            self.send(message(0x700 + self.master_id, b"\x05"))
            self.last_heartbeat = now

    def wait_status(self, expected):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            status = self.read(0x6041, "H")
            if status & 8:
                raise RuntimeError(f"Hexfellow drive fault: status 0x{status:04x}")
            if status & 0x6F == expected:
                return
        raise TimeoutError(f"Hexfellow did not enter status 0x{expected:02x}")

    def prepare(self):
        self.stop()
        self.identify()

    def start(self, watchdog_ms=250):
        watchdog = integer(watchdog_ms, 1, 1, 65535)
        self.prepare()
        self.write(0x1016, "I", (self.master_id << 16) | watchdog, 1, verify=True)
        self.watchdog_ms = watchdog
        self.info.update(watchdog_ms=watchdog, heartbeat_master_id=self.master_id)
        self.write(0x6071, "h", 0)
        limit = math.floor(max(abs(v) for v in self.spec.torque) / self.peak_torque * 1000)
        if limit < 1:
            raise ValueError("Hexfellow torque limit is smaller than one permille")
        self.write(0x6072, "H", limit, verify=True)
        self.write(0x6060, "b", 4, verify=True)
        self.send(message(0, bytes([1, self.motor_id])))
        self.active = True
        self.heartbeat(force=True)
        for control, expected in ((6, 0x21), (7, 0x23), (15, 0x27)):
            self.write(0x6040, "H", control)
            self.wait_status(expected)
        if self.read(0x6061, "b") != 4:
            raise RuntimeError("Hexfellow torque mode not confirmed")

    def command_torque(self, torque):
        if not self.active:
            raise RuntimeError("Start torque mode before commanding torque")
        self.check_torque(torque)
        raw = integer(torque, self.peak_torque / 1000, -1000, 1000)
        low = math.ceil(self.spec.torque[0] / self.peak_torque * 1000)
        high = math.floor(self.spec.torque[1] / self.peak_torque * 1000)
        raw = max(low, min(high, raw))
        self.heartbeat()
        self.write(0x6071, "h", raw)
        return raw * self.peak_torque / 1000

    def read_state(self):
        self.identify()
        position = self.read(0x6064, "i" if self.version == 7 else "f")
        angle_reply = self.last_reply
        velocity = self.read(0x606C, "i" if self.version == 7 else "f")
        if self.version == 7:
            position /= 2**21
            velocity /= 2**21
        torque = self.read(0x6077, "h") * self.peak_torque / 1000
        status = self.read(0x6041, "H")
        if self.active and self.read(0x6061, "b") != 4:
            raise RuntimeError("Hexfellow left torque mode during acquisition")
        faults = self.read(0x603F, "H")
        if faults or status & 8:
            raise RuntimeError(f"Hexfellow faults: 0x{faults:04x}, status 0x{status:04x}")
        mode = 2 if status & 0x6F == 0x27 else 0
        return State(
            position=position * math.tau,
            velocity=velocity * math.tau,
            torque=torque,
            mode=mode,
            faults=faults,
            statusword=status,
            timestamp=angle_reply.timestamp,
            arbitration_id=angle_reply.arbitration_id,
        )

    def inspect(self):
        self.identify()
        return {
            **self.info,
            "mode_display": self.read(0x6061, "b"),
            "statusword": self.read(0x6041, "H"),
            "heartbeat_consumer": self.read(0x1016, "I", 1),
        }

    def stop(self):
        # Disable voltage first, including when a preceding SDO timed out.
        self.write(0x6040, "H", 0)
        self.active = False
        if self.read(0x6041, "H") & 4:
            raise RuntimeError("Hexfellow still reports operation enabled after stop")

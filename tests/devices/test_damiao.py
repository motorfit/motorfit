"""Wire behavior, lifecycle failures and recorder integration without hardware."""

import json
import struct
from pathlib import Path

import can
import pytest

from motorfit.acquisition.recorder import record
from motorfit.config import load_setup
from motorfit.devices.damiao.diagnostics import inspect
from motorfit.devices.damiao.protocol import decode_feedback, encode_command, quantize
from motorfit.devices.spec import MotorSpec

ROOT = Path(__file__).resolve().parents[2]


def setup():
    config = load_setup(ROOT / "configs/setups/dm4310_pendulum.toml")
    config["coordinate"]["zero_rad"] = 0.0
    config["recording"].update(duration_s=0.03, kp=20, kd=0.8)
    return config


def status(code=0, identifier=17):
    return can.Message(
        arbitration_id=identifier,
        is_extended_id=False,
        data=bytes([code << 4 | 1, 0x7F, 0xFF, 0x7F, 0xF7, 0xFF, 35, 36]),
    )


def test_damiao_golden_bytes_and_exact_quantization():
    spec = MotorSpec.from_dict(setup()["motor"])
    # Independent packing fixture: 16-bit P=0x7fff; four 12-bit fields=0x7ff.
    frame = encode_command(0, 0, 250, 2.5, 0, spec=spec, motor_id=1)
    assert bytes(frame.data) == bytes.fromhex("7fff7ff7ff7ff7ff")
    assert not frame.is_extended_id and frame.arbitration_id == 1
    assert quantize(0, -30, 30) == pytest.approx(-30 / 4095)
    assert quantize(20, 0, 500) == pytest.approx(163 * 500 / 4095)
    assert bytes(encode_command(-12.5, -30, 0, 0, -10, spec=spec, motor_id=1).data) == bytes(8)
    assert bytes(encode_command(12.5, 30, 500, 5, 10, spec=spec, motor_id=1).data) == b"\xff" * 8
    with pytest.raises(ValueError, match="representable"):
        encode_command(0, 0, 501, 0, 0, spec=spec, motor_id=1)
    feedback = decode_feedback(status(1), spec=spec, motor_id=1, feedback_id=17)
    assert feedback.mode == 2 and feedback.status_code == 1 and feedback.faults == 0
    assert feedback.rotor_temperature == 36
    assert feedback.position == pytest.approx(-12.5 / 65535)
    assert feedback.torque == pytest.approx(-10 / 4095)


def test_unrelated_frames_and_registers_do_not_become_motion_samples():
    spec = MotorSpec.from_dict(setup()["motor"])
    frames = [status(1, identifier=18), status(1), status(1), status(1)]
    frames[1].is_extended_id = True
    frames[2].is_error_frame = True
    frames[3].data[0] = 0x12  # Wrong motor nibble, despite matching CAN identifier.
    for rid in [9, 21, 36, 60, 81]:
        frames.append(
            can.Message(
                arbitration_id=17,
                is_extended_id=False,
                data=struct.pack("<HBBf", 1, 0x33, rid, 24.0),
            )
        )
    assert all(decode_feedback(f, spec=spec, motor_id=1, feedback_id=17) is None for f in frames)


class DeviceBus:
    def __init__(self, fail=None):
        self.now = 100.0
        self.pending = [status(1)]  # A stale enabled frame must be logged/discarded.
        self.events = []
        self.registers = {9: 0, 10: 2, 21: 12.5, 22: 30.0, 23: 10.0}
        self.enabled = False
        self.closed = False
        self.fail = fail
        self.motion = 0

    def send(self, frame, timeout):
        assert not self.pending, "Sent a request before draining the previous response"
        self.events.append(frame)
        b = frame.data
        if frame.arbitration_id == 0x7FF and b[2] in (0x33, 0x55):
            rid = b[3]
            if b[2] == 0x55:
                self.registers[rid] = struct.unpack("<I", b[4:])[0]
            value = self.registers.get(rid, 24.0 if rid in (17, 18, 20, 60) else 1)
            if self.fail == "range" and rid == 22:
                value = 45.0
            fmt = "f" if isinstance(value, float) else "I"
            reply = bytes(b[:4]) + struct.pack("<" + fmt, value)
            self.pending.append(can.Message(arbitration_id=17, is_extended_id=False, data=reply))
            return
        if bytes(b) == b"\xff" * 7 + b"\xfd":
            self.enabled = False
        elif bytes(b) == b"\xff" * 7 + b"\xfc":
            assert self.registers[10] == 1 and self.registers[9] == 2000
            self.enabled = True
        elif frame.arbitration_id == 1:
            self.motion += 1
            if self.fail == "timeout":
                return
            if self.fail == "fault":
                self.pending.append(status(0xB))
                return
        else:
            assert frame.arbitration_id == 0x7FF and b[2] == 0xCC
        self.pending.append(status(int(self.enabled)))

    def recv(self, timeout):
        self.now += 0.0001 if self.pending else timeout
        return self.pending.pop(0) if self.pending else None

    def shutdown(self):
        self.closed = True


def connect(monkeypatch, fail=None):
    import time

    bus = DeviceBus(fail)
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    monkeypatch.setattr(time, "monotonic", lambda: bus.now)
    monkeypatch.setattr(time, "sleep", lambda seconds: setattr(bus, "now", bus.now + seconds))
    return bus


def test_native_recorder_bam_metadata_and_shutdown(monkeypatch, tmp_path):
    bus = connect(monkeypatch)
    config = setup()
    raw = record(config, tmp_path / "run")
    data = json.loads(raw.read_text())
    assert data["completed"] and data["motor_spec"]["family"] == "damiao"
    assert data["kp_encoded"] == pytest.approx(163 * 500 / 4095)
    assert data["goal_speed"] == pytest.approx(-30 / 4095)
    assert data["feedforward_torque"] == pytest.approx(-10 / 4095)
    assert data["entries"] and data["entries"][0]["timestamp"] == 0
    assert {row["feedback_type"] for row in data["entries"]} == {0}
    assert all(row["torque_enable"] == (row["status_code"] == 1) for row in data["entries"])
    assert data["entries"] == [
        json.loads(s) for s in raw.with_name("samples.jsonl").read_text().splitlines()
    ]
    assert not bus.enabled and bus.closed
    assert bytes(bus.events[-1].data) == b"\xff" * 7 + b"\xfd"
    assert not any(f.arbitration_id == 0x7FF and f.data[2] == 0xAA for f in bus.events)


@pytest.mark.parametrize(
    "failure,exception",
    [
        ("timeout", TimeoutError),
        ("range", ValueError),
        ("fault", RuntimeError),
    ],
)
def test_failed_recording_stops_and_retains_evidence(monkeypatch, tmp_path, failure, exception):
    bus = connect(monkeypatch, failure)
    with pytest.raises(exception):
        record(setup(), tmp_path / "run")
    data = json.loads((tmp_path / "run/raw.json").read_text())
    assert not data["completed"] and data["error"]
    assert not bus.enabled and bus.closed
    assert bytes(bus.events[-1].data) == b"\xff" * 7 + b"\xfd"
    assert (tmp_path / "run/frames.jsonl").read_text()
    if failure == "range":
        assert bus.motion == 0 and data["entries"] == []


def test_inspection_is_read_only(monkeypatch, tmp_path):
    bus = connect(monkeypatch)
    result = inspect(setup(), tmp_path / "inspection.json")
    assert result["parameters"]["PMAX"]["value"] == 12.5
    assert bus.closed
    assert all(f.arbitration_id == 0x7FF and f.data[2] == 0x33 for f in bus.events)

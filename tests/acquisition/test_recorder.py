"""Real RobStride driver/recorder contracts using an in-memory CAN peer."""

import json
import struct

import can
import pytest

import motorfit.acquisition.recorder as recorder
from motorfit.devices.robstride.protocol import quantize


class DeviceBus:
    def __init__(self, *, interrupt_after=None, reply_delay=0.0001):
        self.now = 100.0
        self.events, self.registers = [], {}
        self.mode, self.motion = 0, 0
        self.closed = False
        self.interrupt_after, self.reply_delay = interrupt_after, reply_delay
        # A valid but stale enabled frame must be discarded before startup.
        self.pending = [
            can.Message(
                arbitration_id=0x02807FFF,
                is_extended_id=True,
                data=bytes.fromhex("96d87fff7fff0118"),
            )
        ]

    def send(self, message, timeout):
        assert not self.pending, "A new request must wait for the preceding reply"
        self.events.append(("tx", message))
        kind = message.arbitration_id >> 24
        response_id = 0x02007FFF
        payload = bytes.fromhex("96d87fff7fff0118")
        if kind == 4:
            self.mode = 0
        elif kind == 3:
            assert self.registers == {0x7005: bytes(4), 0x7028: struct.pack("<I", 2000)}
            self.mode = 2
        elif kind == 24:
            assert bytes(message.data) == bytes.fromhex("0102030405060000")
        elif kind in (17, 18):
            index = struct.unpack_from("<H", message.data)[0]
            if kind == 18:
                self.registers[index] = bytes(message.data[4:])
            else:
                response_id = 0x11007FFF
                payload = struct.pack("<H2x", index) + self.registers[index]
        else:
            assert kind in (1, 2)
            if kind == 1:
                self.motion += 1
                if self.motion == self.interrupt_after:
                    raise KeyboardInterrupt()
        if kind != 17:
            response_id |= self.mode << 22
        self.pending.append(
            can.Message(
                arbitration_id=response_id,
                is_extended_id=True,
                data=payload,
                timestamp=1700000000 + self.now,
            )
        )

    def recv(self, timeout):
        self.now += self.reply_delay if self.pending else timeout
        if not self.pending:
            return None
        frame = self.pending.pop(0)
        self.events.append(("rx", frame))
        return frame

    def shutdown(self):
        self.closed = True


def setup(monkeypatch, trajectory="sin_time_square", **bus_options):
    bus = DeviceBus(**bus_options)
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    monkeypatch.setattr(recorder.time, "monotonic", lambda: bus.now)
    monkeypatch.setattr(recorder.time, "sleep", lambda dt: setattr(bus, "now", bus.now + dt))
    config = {
        "motor": {
            "name": "test_motor",
            "family": "robstride",
            "position": [-10.0, 10.0],
            "velocity": [-20.0, 20.0],
            "torque": [-8.0, 8.0],
            "kp": [0.0, 400.0],
            "kd": [0.0, 4.0],
            "source": "synthetic test profile",
        },
        "device": {
            "channel": "unused",
            "motor_id": 127,
            "host_id": 255,
            "timeout_s": 0.2,
            "watchdog_ms": 100,
        },
        "coordinate": {"zero_rad": 0.25, "convention": "downward-positive-encoder"},
        "recording": {
            "hz": 100,
            "kp": 30,
            "kd": 2,
            "duration_s": 0.03,
            "trajectory": trajectory,
            "amplitude": 1,
            "sweep_k": 0.1,
        },
        "fixture": {
            "mass": 0.1248,
            "arm_mass": 0.11,
            "length": 0.2,
            "arm_com": 0.09,
            "arm_inertia": 0.0014,
            "hub_inertia": 0.00000216,
            "vin": 23,
        },
    }
    return config, bus


@pytest.mark.parametrize("trajectory", ["sin_time_square", "nothing"])
def test_real_driver_recorder_wire_contract(monkeypatch, tmp_path, trajectory):
    config, bus = setup(monkeypatch, trajectory)
    path = recorder.record(config, tmp_path / "run")
    data = json.loads(path.read_text())
    kinds = [frame.arbitration_id >> 24 for direction, frame in bus.events if direction == "tx"]
    if trajectory == "nothing":
        assert kinds == [4, 24, 2, 2, 2, 4]
    else:
        assert kinds == [4, 24, 18, 17, 18, 17, 3, 1, 1, 1, 4]
    assert [direction for direction, _ in bus.events] == ["rx"] + ["tx", "rx"] * len(kinds)
    assert data["completed"] and len(data["entries"]) == 3
    assert {entry["feedback_type"] for entry in data["entries"]} == {2}
    assert data["error"] is None and data["motor_spec"]["name"] == "test_motor"
    assert data["kp"] == 30 and data["kd"] == 2
    assert data["kp_encoded"] == quantize(30, 0, 400)
    assert data["kd_encoded"] == quantize(2, 0, 4)
    assert data["goal_speed"] == quantize(0, -20, 20)
    assert data["feedforward_torque"] == quantize(0, -8, 8)
    assert data["entries"][0]["timestamp"] == 0
    assert data["entries"][0]["position"] == pytest.approx(0x96D8 / 65535 * 20 - 10 - 0.25)
    assert [row["transaction_id"] for row in data["entries"]] == [1, 2, 3]
    assert data["entries"] == [
        json.loads(line) for line in path.with_name("samples.jsonl").read_text().splitlines()
    ]
    frames = [json.loads(line) for line in path.with_name("frames.jsonl").read_text().splitlines()]
    assert [frame["direction"] for frame in frames] == [direction for direction, _ in bus.events]
    command_times = [row["command_monotonic_time"] for row in data["entries"]]
    assert [t - command_times[0] for t in command_times] == pytest.approx([0, 0.01, 0.02])
    assert all(row["input_volts"] == 23 for row in data["entries"])
    assert data["input_volts_source"] == "configured_supply"
    assert data["telemetry_file"] is None
    assert not path.with_name("telemetry.jsonl").exists()
    if trajectory == "nothing":
        assert not any(row["torque_enable"] for row in data["entries"])
    else:
        commands = [
            f for direction, f in bus.events if direction == "tx" and f.arbitration_id >> 24 == 1
        ]
        for row, frame in zip(data["entries"], commands, strict=True):
            encoded_position = struct.unpack_from(">H", frame.data)[0] / 65535 * 20 - 10
            assert row["goal_position"] == pytest.approx(encoded_position - 0.25)
            assert row["torque_enable"]
    assert bus.closed and bus.mode == 0


def test_interrupt_preserves_samples_and_stops(monkeypatch, tmp_path):
    config, bus = setup(monkeypatch, interrupt_after=2)
    with pytest.raises(KeyboardInterrupt):
        recorder.record(config, tmp_path / "run")
    data = json.loads((tmp_path / "run/raw.json").read_text())
    assert not data["completed"] and data["error"].startswith("KeyboardInterrupt")
    assert len(data["entries"]) == 1
    assert data["entries"] == [
        json.loads(line) for line in (tmp_path / "run/samples.jsonl").read_text().splitlines()
    ]
    assert (tmp_path / "run/frames.jsonl").read_text()
    assert bus.events[-2][1].arbitration_id >> 24 == 4
    assert bus.closed and bus.mode == 0


def test_slow_reply_skips_missed_ticks_without_command_bursts(monkeypatch, tmp_path):
    config, bus = setup(monkeypatch, reply_delay=0.025)
    path = recorder.record(config, tmp_path / "run")
    assert bus.motion == 1
    assert len(json.loads(path.read_text())["entries"]) == 1

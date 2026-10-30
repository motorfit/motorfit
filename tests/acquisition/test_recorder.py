import json
import struct
from types import SimpleNamespace

import can
import pytest

import motorfit.acquisition.recorder as recorder
from motorfit.devices.robstride.motor import Motor
from motorfit.devices.robstride.protocol import quantize


class Clock:
    now = 100.0

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


class FakeMotor:
    def __init__(self, clock, fail=None, **kwargs):
        self.clock, self.fail = clock, fail
        self.callback = kwargs["on_frame"]
        self.commands = []
        self.stopped = False
        self.closed = False
        self.started = False

    def frame(self, direction):
        self.callback(
            direction,
            can.Message(
                timestamp=1700000000.0 + self.clock.now,
                arbitration_id=0x02007FFD,
                data=b"12345678",
                is_extended_id=True,
            ),
        )

    def start(self, watchdog_ms):
        self.started = True
        self.frame("tx")

    def command(self, *values):
        self.commands.append((self.clock.now, values))
        self.frame("tx")
        return self.feedback()

    def feedback(self):
        if self.fail is TimeoutError:
            self.clock.now += 0.2
            raise TimeoutError("No type-2 reply")
        if len(self.commands) == 2 and self.fail:
            raise self.fail("interrupted receive")
        self.clock.now += 0.001
        self.frame("rx")
        return SimpleNamespace(
            position=0.35,
            velocity=0.4,
            torque=0.2,
            temperature=35,
            faults=0,
            mode=2 if self.started else 0,
            motor_id=127,
            timestamp=1700000000 + self.clock.now,
            communication_type=2,
            arbitration_id=0x02807FFF if self.started else 0x02007FFF,
        )

    def stop(self):
        self.stopped = True
        self.started = False
        self.frame("tx")

    def close(self):
        self.closed = True


def setup(monkeypatch, fail=None, trajectory="sin_time_square"):
    clock = Clock()
    monkeypatch.setattr(recorder.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(recorder.time, "sleep", clock.sleep)
    instances = []

    def factory(**kwargs):
        motor = FakeMotor(clock, fail=fail, **kwargs)
        instances.append(motor)
        return motor

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
    return config, factory, instances


@pytest.mark.parametrize("failure", [KeyboardInterrupt, TimeoutError])
def test_record_abort_preserves_samples_and_stops(monkeypatch, tmp_path, failure):
    config, factory, instances = setup(monkeypatch, fail=failure)
    with pytest.raises(failure):
        recorder.record(config, tmp_path / "run", motor_factory=factory)
    data = json.loads((tmp_path / "run/raw.json").read_text())
    assert not data["completed"]
    assert data["error"].startswith(failure.__name__)
    assert len(data["entries"]) == (0 if failure is TimeoutError else 1)
    assert instances[0].stopped and instances[0].closed
    assert (tmp_path / "run/frames.jsonl").read_text()
    assert [
        json.loads(line) for line in (tmp_path / "run/samples.jsonl").read_text().splitlines()
    ] == data["entries"]


def test_mixed_telemetry_rejected_before_opening_motor(monkeypatch, tmp_path):
    config, factory, instances = setup(monkeypatch)
    config["recording"].update(telemetry_hz=20, duration_s=0.12)
    with pytest.raises(ValueError, match="In-loop telemetry is not supported"):
        recorder.record(config, tmp_path / "run", motor_factory=factory)
    assert not instances
    assert not (tmp_path / "run").exists()


def test_slow_reply_skips_missed_ticks_without_command_bursts(monkeypatch, tmp_path):
    config, factory, instances = setup(monkeypatch)
    original = FakeMotor.feedback

    def slow_feedback(self):
        self.clock.now += 0.024
        return original(self)

    monkeypatch.setattr(FakeMotor, "feedback", slow_feedback)
    path = recorder.record(config, tmp_path / "run", motor_factory=factory)
    assert [t for t, _ in instances[0].commands] == [100]
    assert len(json.loads(path.read_text())["entries"]) == 1


@pytest.mark.parametrize("trajectory", ["sin_time_square", "nothing"])
def test_real_driver_recorder_wire_contract(monkeypatch, tmp_path, trajectory):
    config, _, _ = setup(monkeypatch, trajectory=trajectory)
    pending, events, registers = [], [], {}
    mode = 0
    closed = False

    class DeviceBus:
        def send(self, message, timeout):
            nonlocal mode
            # A second request before consuming the previous reply is a failure.
            assert not pending
            events.append(("tx", message))
            kind = message.arbitration_id >> 24
            response_id = 0x02007FFF
            payload = bytes.fromhex("96d87fff7fff0118")
            if kind == 4:
                mode = 0
            elif kind == 3:
                assert registers == {0x7005: bytes(4), 0x7028: struct.pack("<I", 2000)}
                mode = 2
            elif kind == 24:
                assert bytes(message.data) == bytes.fromhex("0102030405060000")
            elif kind in (17, 18):
                index = struct.unpack_from("<H", message.data)[0]
                if kind == 18:
                    registers[index] = bytes(message.data[4:])
                else:
                    response_id = 0x11007FFF
                    payload = struct.pack("<H2x", index) + registers[index]
            else:
                assert kind == (1 if trajectory == "sin_time_square" else 2)
            if kind != 17:
                response_id |= mode << 22
            pending.append(
                can.Message(
                    arbitration_id=response_id,
                    is_extended_id=True,
                    data=payload,
                    timestamp=1700000000 + recorder.time.monotonic(),
                )
            )

        def recv(self, timeout):
            if pending:
                frame = pending.pop(0)
                recorder.time.sleep(0.0001)
                events.append(("rx", frame))
                return frame
            recorder.time.sleep(timeout)
            return None

        def shutdown(self):
            nonlocal closed
            closed = True

    monkeypatch.setattr(can, "Bus", lambda **kwargs: DeviceBus())
    path = recorder.record(config, tmp_path / "run", motor_factory=Motor)
    data = json.loads(path.read_text())
    kinds = [frame.arbitration_id >> 24 for direction, frame in events if direction == "tx"]
    if trajectory == "nothing":
        assert kinds == [4, 24, 2, 2, 2, 4]
    else:
        assert kinds == [4, 24, 18, 17, 18, 17, 3, 1, 1, 1, 4]
    assert [direction for direction, _ in events] == ["tx", "rx"] * len(kinds)
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
    assert [frame["direction"] for frame in frames] == [direction for direction, _ in events]
    command_times = [row["command_monotonic_time"] for row in data["entries"]]
    assert [t - command_times[0] for t in command_times] == pytest.approx([0, 0.01, 0.02])
    assert all(row["input_volts"] == 23 for row in data["entries"])
    assert data["input_volts_source"] == "configured_supply"
    assert data["telemetry_file"] is None
    assert not path.with_name("telemetry.jsonl").exists()
    if trajectory == "nothing":
        assert not any(row["torque_enable"] for row in data["entries"])
    else:
        commands = [f for direction, f in events if direction == "tx" and f.arbitration_id >> 24 == 1]
        for row, frame in zip(data["entries"], commands, strict=True):
            encoded_position = struct.unpack_from(">H", frame.data)[0] / 65535 * 20 - 10
            assert row["goal_position"] == pytest.approx(encoded_position - 0.25)
            assert row["torque_enable"]
    assert closed and mode == 0

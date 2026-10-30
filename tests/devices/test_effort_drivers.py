"""Wire-contract tests: native codecs, addressed replies, cleanup, firmware units."""

import math
import struct
import tomllib
from pathlib import Path

import can
import pytest

from motorfit.devices.registry import connection, driver
from motorfit.devices.spec import MotorSpec
from motorfit.devices.transactions import message

ROOT = Path(__file__).parents[2]
PROFILES = [
    "myactuator/rmd_x_v3",
    "hightorque/ht_can",
    "hexfellow/canopen_v07",
    "hexfellow/canopen_v08",
]


def spec_for(profile):
    return MotorSpec.from_dict(tomllib.loads((ROOT / f"configs/motors/{profile}.toml").read_text()))


class DeviceBus:
    """A small device-side test peer; no sockets and no shared production codecs."""

    def __init__(self, family, version=8, clock=None):
        self.family, self.version, self.clock = family, version, clock
        self.pending, self.sent = [], []
        self.closed = False
        self.fail_command = False
        self.sdo_abort = None
        self.wrong_size = False
        self.wrong_mode = False
        self.values = {
            (0x1016, 1): ("I", 0),
            (0x1018, 3): ("I", version),
            (0x6076, 0): ("I", 10000) if version == 7 else ("f", 10.0),
            (0x6064, 0): ("i", 0) if version == 7 else ("f", 0.0),
            (0x606C, 0): ("i", 0) if version == 7 else ("f", 0.0),
            (0x6077, 0): ("h", 0),
            (0x6041, 0): ("H", 0x40),
            (0x603F, 0): ("H", 0),
            (0x6061, 0): ("b", 0),
        }
        self.angle_centidegrees, self.speed_dps, self.current_centiamps = 0, 0, 0
        self.ht_values = (0, 0, 0)
        self.faults = 0

    def send(self, frame, timeout):
        self.sent.append(frame)
        b = bytes(frame.data)
        if self.family == "myactuator":
            assert frame.arbitration_id == 0x141 and not frame.is_extended_id
            if b[0] == 0xA1 and self.fail_command:
                return
            reply = bytearray(b)
            if b[0] in (0x9C, 0xA1):
                reply[1:] = struct.pack("<bhhh", 32, self.current_centiamps, self.speed_dps, 123)
            elif b[0] == 0x92:
                reply[4:] = struct.pack("<i", self.angle_centidegrees)
            elif b[0] == 0x9A:
                reply[6:] = struct.pack("<H", self.faults)
            elif b[0] == 0xB2:
                reply[4:] = struct.pack("<I", 20240101)
            self.pending.append(message(0x241, reply))
        elif self.family == "hightorque":
            assert frame.arbitration_id == 0x8001 and frame.is_extended_id
            if b[:2] == b"\x17\x01" and not self.fail_command:
                self.pending.append(
                    message(1, b"\x27\x01" + struct.pack("<hhh", *self.ht_values), extended=True)
                )
        else:
            if frame.arbitration_id != 0x601:  # NMT/heartbeat have no SDO reply.
                return
            key = (int.from_bytes(b[1:3], "little"), b[3])
            if self.sdo_abort == key:
                reply = b"\x80" + b[1:4] + bytes.fromhex("00000206")
            elif b[0] == 0x40:
                fmt, value = self.values[key]
                raw = struct.pack("<" + fmt, value)
                command = {1: 0x4F, 2: 0x4B, 4: 0x43}[len(raw)]
                if self.wrong_size:
                    command = 0x4B if command == 0x43 else 0x43
                reply = bytes([command]) + b[1:4] + raw.ljust(4, b"\x00")
            else:
                n = {0x2F: 1, 0x2B: 2, 0x23: 4}[b[0]]
                fmt = {1: "B", 2: "H", 4: "I"}[n]
                self.values[key] = (fmt, int.from_bytes(b[4 : 4 + n], "little"))
                if key == (0x6040, 0):
                    self.values[(0x6041, 0)] = ("H", {0: 0x40, 6: 0x21, 7: 0x23, 15: 0x27}[b[4]])
                if key == (0x6060, 0):
                    self.values[(0x6061, 0)] = ("b", 3 if self.wrong_mode else b[4])
                reply = b"\x60" + b[1:4] + bytes(4)
            self.pending.append(message(0x581, reply))

    def recv(self, timeout):
        if self.clock:
            self.clock.now += 0.0002 if self.pending else timeout
        return self.pending.pop(0) if self.pending else None

    def shutdown(self):
        self.closed = True


@pytest.mark.parametrize("profile", PROFILES)
def test_signed_wire_effort_and_read_units(profile, monkeypatch):
    spec = spec_for(profile)
    bus = DeviceBus(spec.family, spec.protocol.get("firmware_version", 8))
    opened = []
    monkeypatch.setattr(can, "Bus", lambda **kw: opened.append(kw) or bus)
    motor = driver(spec.family)(spec, host_id=None)
    motor.start(watchdog_ms=0 if spec.family == "hightorque" else 250)
    actual = motor.command_torque(-0.23)
    assert actual == pytest.approx(-0.23)
    if spec.family == "myactuator":
        assert bytes(bus.sent[-1].data) == bytes.fromhex("a1000000e9ff0000")
        bus.angle_centidegrees, bus.speed_dps, bus.current_centiamps = -9000, -180, -25
        state = motor.read_state()
        assert state.position == pytest.approx(-math.pi / 2)
        assert state.velocity == pytest.approx(-math.pi)
        assert state.torque == pytest.approx(-0.25)
        assert state.mode == -1
        assert any(bytes(f.data) == bytes.fromhex("b3000000fa000000") for f in bus.sent)
    elif spec.family == "hightorque":
        assert bytes(bus.sent[-1].data) == bytes.fromhex("0513e9ff")
        bus.ht_values = (-1250, -2000, -25)
        state = motor.read_state()
        assert state.position == pytest.approx(-math.pi / 4)
        assert state.velocity == pytest.approx(-math.pi)
        assert state.torque == pytest.approx(-0.25)
        assert state.mode == -1 and state.faults == -1 and state.temperature is None
    else:
        assert bytes(bus.sent[-1].data) == bytes.fromhex("2b716000e9ff0000")
        version = spec.protocol["firmware_version"]
        bus.values[(0x6064, 0)] = ("i", -262144) if version == 7 else ("f", -0.125)
        bus.values[(0x606C, 0)] = ("i", -1048576) if version == 7 else ("f", -0.5)
        bus.values[(0x6077, 0)] = ("h", -25)
        state = motor.read_state()
        assert state.position == pytest.approx(-math.pi / 4)
        assert state.velocity == pytest.approx(-math.pi)
        assert state.torque == pytest.approx(-0.25)
        assert state.mode == 2
        assert opened[0]["fd"]
        assert bus.values[(0x1016, 1)][1] == (126 << 16) | 250
    n = len(bus.sent)
    for invalid in (math.nan, math.inf, 1.01):
        with pytest.raises(ValueError):
            motor.command_torque(invalid)
    assert len(bus.sent) == n
    motor.stop()
    assert not motor.active
    motor.close()
    assert bus.closed


@pytest.mark.parametrize("profile", PROFILES)
def test_wrong_id_and_stale_frames_do_not_satisfy_requests(profile, monkeypatch):
    spec = spec_for(profile)
    bus = DeviceBus(spec.family, spec.protocol.get("firmware_version", 8))
    original = bus.send

    def send(frame, timeout):
        original(frame, timeout)
        # Only wrong-address frames remain after each genuine request.
        for reply in bus.pending:
            reply.arbitration_id += 1

    bus.send = send
    bus.pending.append(message(0x241, bytes(8)))  # Must be drained before TX.
    monkeypatch.setattr(can, "Bus", lambda **kw: bus)
    motor = driver(spec.family)(spec, timeout=0.001)
    with pytest.raises(TimeoutError):
        motor.read_state()
    motor.close()


def test_hex_rejects_revision_abort_bad_sizes_and_mode(monkeypatch):
    spec = spec_for("hexfellow/canopen_v08")
    for issue in ("revision", "abort", "size", "mode"):
        bus = DeviceBus("hexfellow", 7 if issue == "revision" else 8)
        bus.sdo_abort = (0x1018, 3) if issue == "abort" else None
        bus.wrong_size = issue == "size"
        bus.wrong_mode = issue == "mode"
        monkeypatch.setattr(can, "Bus", lambda **kw: bus)
        motor = driver("hexfellow")(spec)
        with pytest.raises((ValueError, RuntimeError)):
            motor.start()
        # No nonzero effort can be sent by failed initialization.
        assert not any(
            bytes(f.data[:4]) == bytes.fromhex("2b716000") and any(f.data[4:6]) for f in bus.sent
        )
        motor.close()


def test_myactuator_current_saturation_and_faults(monkeypatch):
    data = spec_for("myactuator/rmd_x_v3").to_dict()
    data["protocol"] = {"torque_constant_nm_per_a": 2.0, "current_limit_a": 0.153}
    bus = DeviceBus("myactuator")
    monkeypatch.setattr(can, "Bus", lambda **kw: bus)
    motor = driver("myactuator")(MotorSpec.from_dict(data))
    motor.start()
    assert motor.command_torque(1.0) == pytest.approx(0.3)
    assert bytes(bus.sent[-1].data) == bytes.fromhex("a10000000f000000")
    bus.faults = 0x10
    with pytest.raises(RuntimeError, match="faults"):
        motor.read_state()
    motor.close()


def test_high_torque_does_not_fake_watchdog_support(monkeypatch):
    bus = DeviceBus("hightorque")
    monkeypatch.setattr(can, "Bus", lambda **kw: bus)
    motor = driver("hightorque")(spec_for("hightorque/ht_can"))
    with pytest.raises(ValueError, match="watchdog"):
        motor.start(100)
    assert not bus.sent
    motor.close()


def test_new_connections_derive_response_ids():
    for profile, feedback in zip(PROFILES, [0x241, 1, 0x581, 0x581]):
        config = {
            "motor": spec_for(profile).to_dict(),
            "device": {"channel": "unused", "motor_id": 1, "timeout_s": 0.1},
        }
        assert connection(config)["host_id"] == feedback


@pytest.mark.parametrize("profile", PROFILES)
def test_native_record_process_fit_reload_and_evaluate(profile, monkeypatch, tmp_path, capsys):
    """Real native drivers -> recorder -> timed resampling -> real BAM optimizer."""
    import json

    from bam.actuators import actuators

    from motorfit.acquisition.recorder import record
    from motorfit.identification.bam import bam_tool, load_model, process

    class Clock:
        now = 100.0

        def monotonic(self):
            return self.now

        def sleep(self, dt):
            self.now += dt

    spec = spec_for(profile)
    config = dict(
        motor=spec.to_dict(),
        device=dict(
            channel="unused",
            motor_id=1,
            timeout_s=0.1,
            watchdog_ms=0 if spec.family == "hightorque" else 250,
        ),
        fixture=dict(mass=0.1, arm_mass=0.02, length=0.2, vin=24.0),
        coordinate=dict(zero_rad=0.0, convention="downward-positive-encoder"),
        recording=dict(
            hz=20,
            duration_s=0.3,
            trajectory="soccer_sweep",
            amplitude=0.15,
            sweep_k=2,
            kp=3,
            kd=0.15,
        ),
    )
    for i, kp in enumerate((3, 4, 5)):
        config["recording"]["kp"] = kp
        clock = Clock()
        bus = DeviceBus(spec.family, spec.protocol.get("firmware_version", 8), clock)
        with monkeypatch.context() as m:
            import motorfit.acquisition.effort as effort

            m.setattr(can, "Bus", lambda **kw: bus)
            m.setattr(effort.time, "monotonic", clock.monotonic)
            m.setattr(effort.time, "sleep", clock.sleep)
            raw = record(config, tmp_path / f"raw/run{i}")
        data = json.loads(raw.read_text())
        assert data["completed"] and len(data["entries"]) >= 5
        assert data["control_source"] == "recorded_effort"
        assert any(e["control"] > 0 for e in data["entries"])
        assert bus.closed
        assert [
            json.loads(x) for x in raw.with_name("samples.jsonl").read_text().splitlines()
        ] == data["entries"]
        # Mark fixture records as synthetic evidence, never hardware validation.
        data["synthetic"] = True
        raw.write_text(json.dumps(data))
    process(tmp_path / "raw", tmp_path / "logs", 0.025)
    processed = json.loads(next((tmp_path / "logs").glob("*.json")).read_text())
    assert processed["control_source"] == "recorded_effort"
    assert processed["resampling"] == "linear sensors; ZOH effort at command TX times"
    assert processed["entries"][0]["control"] == 0
    params = tmp_path / "fit.json"
    monkeypatch.chdir(tmp_path)
    bam_tool(
        "fit",
        [
            "--logdir",
            str(tmp_path / "logs"),
            "--model",
            "m1",
            "--trials",
            "2",
            "--validation_kp",
            "5",
            "--reset_period",
            "0.05",
            "--output",
            str(params),
        ],
    )
    values = json.loads(params.read_text())
    assert math.isfinite(values["identification"]["training_mae_rad"])
    assert math.isfinite(values["identification"]["validation_mae_rad"])
    del actuators[spec.name]
    model = load_model(params)
    assert model.actuator.spec == spec
    assert model.actuator.__class__.__name__ == "RecordedEffortActuator"
    bam_tool("fit", ["--logdir", str(tmp_path / "logs"), "--eval", "--output", str(params)])
    assert "Score:" in capsys.readouterr().out
    import matplotlib.pyplot as plt

    monkeypatch.setattr(plt, "show", lambda: None)
    bam_tool("plot", ["--logdir", str(tmp_path / "logs"), "--sim", "--params", str(params)])
    plt.close("all")


@pytest.mark.parametrize("profile", PROFILES)
def test_failed_state_read_closes_and_disables(profile, monkeypatch, tmp_path):
    import json

    from motorfit.acquisition.recorder import record

    spec = spec_for(profile)
    bus = DeviceBus(spec.family, spec.protocol.get("firmware_version", 8))
    original = bus.send

    def failing_send(frame, timeout):
        b = bytes(frame.data)
        if spec.family == "myactuator" and b[0] == 0x9C:
            return
        if spec.family == "hightorque" and b[:2] == b"\x17\x01":
            return
        if spec.family == "hexfellow" and b[:4] == bytes.fromhex("40646000"):
            return
        original(frame, timeout)

    bus.send = failing_send
    monkeypatch.setattr(can, "Bus", lambda **kw: bus)
    config = dict(
        motor=spec.to_dict(),
        device=dict(
            channel="unused",
            motor_id=1,
            timeout_s=0.01,
            watchdog_ms=0 if spec.family == "hightorque" else 250,
        ),
        fixture=dict(mass=0.1, arm_mass=0.02, length=0.2, vin=24),
        coordinate=dict(zero_rad=0),
        recording=dict(hz=20, duration_s=1, trajectory="soccer_sweep", kp=3, kd=0.15),
    )
    with pytest.raises(TimeoutError):
        record(config, tmp_path / "run")
    data = json.loads((tmp_path / "run/raw.json").read_text())
    assert not data["completed"] and "TimeoutError" in data["error"]
    assert bus.closed
    assert any(
        (spec.family == "myactuator" and f.data[0] == 0x80)
        or (spec.family == "hightorque" and bytes(f.data) == b"\x01\x00\x00")
        or (spec.family == "hexfellow" and bytes(f.data) == bytes.fromhex("2b40600000000000"))
        for f in bus.sent[-2:]
    )


@pytest.mark.parametrize("profile", ["myactuator/rmd_x_v3", "hexfellow/canopen_v08"])
def test_stop_is_sent_even_if_receive_queue_cannot_drain(profile, monkeypatch):
    spec = spec_for(profile)
    bus = DeviceBus(spec.family)
    monkeypatch.setattr(can, "Bus", lambda **kw: bus)
    motor = driver(spec.family)(spec)

    def busy():
        raise TimeoutError("queue remains busy")

    motor.drain = busy
    with pytest.raises(TimeoutError, match="busy"):
        motor.stop()
    last = bytes(bus.sent[-1].data)
    assert last == (
        bytes.fromhex("8000000000000000")
        if spec.family == "myactuator"
        else bytes.fromhex("2b40600000000000")
    )
    motor.close()


@pytest.mark.parametrize("profile", PROFILES)
def test_read_and_inspect_never_enable_or_write(profile, monkeypatch, tmp_path):
    import json

    from motorfit.devices.diagnostics import inspect

    spec = spec_for(profile)
    bus = DeviceBus(spec.family, spec.protocol.get("firmware_version", 8))
    monkeypatch.setattr(can, "Bus", lambda **kw: bus)
    result = inspect(
        {"motor": spec.to_dict(), "device": {"channel": "unused", "motor_id": 1, "timeout_s": 0.1}},
        tmp_path / "inspect.json",
    )
    assert json.loads((tmp_path / "inspect.json").read_text()) == result
    if spec.family == "myactuator":
        assert all(f.data[0] in (0xB2, 0x70, 0x9C, 0x92, 0x9A) for f in bus.sent)
    elif spec.family == "hightorque":
        assert all(bytes(f.data[:2]) == b"\x17\x01" for f in bus.sent)
    else:
        assert all(f.arbitration_id == 0x601 and f.data[0] == 0x40 for f in bus.sent)
    assert bus.closed


def test_hex_detects_mode_change_during_recording(monkeypatch):
    bus = DeviceBus("hexfellow")
    monkeypatch.setattr(can, "Bus", lambda **kw: bus)
    motor = driver("hexfellow")(spec_for("hexfellow/canopen_v08"))
    motor.start()
    bus.values[(0x6061, 0)] = ("b", 3)
    with pytest.raises(RuntimeError, match="left torque mode"):
        motor.read_state()
    motor.stop()
    motor.close()

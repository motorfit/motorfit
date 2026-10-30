import json
import struct
import tomllib
from pathlib import Path

import can
import pytest

from motorfit.devices.robstride import (
    Motor,
    MotorSpec,
    decode_feedback,
    encode_command,
    quantize,
)

MODEL_DIR = Path(__file__).parents[2] / "configs/motors/robstride"
MODEL_FILES = sorted(MODEL_DIR.glob("*.toml"))


def load_spec(path):
    return MotorSpec.from_dict(tomllib.loads(path.read_text()))


@pytest.fixture
def spec():
    return load_spec(MODEL_DIR / "rs05.toml")


@pytest.mark.parametrize("path", MODEL_FILES, ids=lambda path: path.stem)
def test_model_roundtrip_and_wire_boundaries(path):
    model = load_spec(path)
    assert MotorSpec.from_dict(json.loads(json.dumps(model.to_dict()))) == model
    for side, word in ((0, 0), (1, 65535)):
        command = encode_command(
            model.position[side],
            model.velocity[side],
            model.kp[side],
            model.kd[side],
            model.torque[side],
            spec=model,
        )
        assert command.arbitration_id == (1 << 24) | (word << 8) | 127
        assert bytes(command.data) == struct.pack(">HHHH", word, word, word, word)
        for index, limits in enumerate(
            (model.position, model.velocity, model.kp, model.kd, model.torque)
        ):
            values = [
                model.position[side],
                model.velocity[side],
                model.kp[side],
                model.kd[side],
                model.torque[side],
            ]
            values[index] = limits[side] + (-0.01 if side == 0 else 0.01)
            with pytest.raises(ValueError):
                encode_command(*values, spec=model)


def test_feedback_uses_selected_model_ranges():
    message = can.Message(
        arbitration_id=0x02007FFF,
        is_extended_id=True,
        data=bytes.fromhex("ffffffffffff01f4"),
    )
    decoded = []
    for path in MODEL_FILES:
        model = load_spec(path)
        feedback = decode_feedback(message, spec=model)
        assert feedback.position == pytest.approx(model.position[1])
        assert feedback.velocity == pytest.approx(model.velocity[1])
        assert feedback.torque == pytest.approx(model.torque[1])
        decoded.append((feedback.velocity, feedback.torque))
    assert {"rs01", "rs02", "rs05", "rs06"} <= {path.stem for path in MODEL_FILES}
    assert len(set(decoded)) > 1


def test_unknown_family_is_not_robstride(spec):
    data = spec.to_dict()
    data["family"] = "other"
    with pytest.raises(ValueError, match="Unsupported motor family"):
        MotorSpec.from_dict(data)


def test_motion_wire_bytes_and_rs05_ranges(spec):
    message = encode_command(0, 0, 30, 2, 0, spec=spec)
    assert message.arbitration_id == 0x017FFF7F
    assert bytes(message.data) == bytes.fromhex("7fff7fff0f5c6666")
    assert message.is_extended_id
    assert quantize(30, 0, 500) == pytest.approx(29.9992370489)
    maximum = encode_command(12.57, 50, 500, 5, 5.5, spec=spec)
    assert maximum.arbitration_id == 0x01FFFF7F
    assert bytes(maximum.data) == b"\xff" * 8
    for field, value in ((0, 12.58), (1, 50.1), (2, 501), (3, 5.1), (4, 5.6), (0, float("nan"))):
        command = [0, 0, 30, 2, 0]
        command[field] = value
        with pytest.raises(ValueError):
            encode_command(*command, spec=spec)


def status(*, kind=2, mode=0, faults=0, motor_id=127, host_id=255):
    return can.Message(
        arbitration_id=(kind << 24) | (mode << 22) | (faults << 16) | (motor_id << 8) | host_id,
        is_extended_id=True,
        timestamp=123.25,
        data=bytes.fromhex("96d87fff7fff0118"),
    )


def parameter(index, value, format="I", *, motor_id=127, host_id=255, rejected=False):
    return can.Message(
        arbitration_id=(17 << 24) | (int(rejected) << 16) | (motor_id << 8) | host_id,
        is_extended_id=True,
        data=struct.pack("<H2x", index) + struct.pack("<" + format, value).ljust(4, b"\0"),
    )


def test_feedback_accepts_only_addressed_type2(spec):
    feedback = decode_feedback(status(mode=2, faults=5), spec=spec)
    assert feedback.position == pytest.approx(2.2435536736095205)
    assert (feedback.temperature, feedback.faults, feedback.mode) == (28, 5, 2)
    assert (feedback.motor_id, feedback.timestamp) == (127, 123.25)
    assert feedback.communication_type == 2
    assert feedback.arbitration_id == 0x02857FFF
    for message in (
        status(kind=24),
        status(kind=17),
        status(motor_id=1),
        status(host_id=253),
        can.Message(arbitration_id=0x200, is_extended_id=False, data=bytes(8)),
        can.Message(arbitration_id=0x02007FFF, is_extended_id=True, data=bytes(7)),
        can.Message(arbitration_id=0x02007FFF, is_extended_id=True, data=bytes(8), dlc=4),
        can.Message(arbitration_id=0x02007FFF, is_extended_id=True, is_remote_frame=True),
        can.Message(arbitration_id=0x02007FFF, is_extended_id=True, is_error_frame=True),
    ):
        assert decode_feedback(message, spec=spec) is None


@pytest.mark.parametrize(
    "values,identifier,payload",
    [
        ((0, 0, 5, 0.2, 0), 0x017FFF7F, "7fff7fff028f0a3d"),
        ((2.2436695, 0, 5, 0.2, 0), 0x017FFF7F, "96d87fff028f0a3d"),
        ((0.5, 1, 5, 0.2, 1), 0x0197457F, "8516828e028f0a3d"),
    ],
)
def test_rs05_matches_independently_executed_embedded_c_vectors(spec, values, identifier, payload):
    # Golden vectors generated by executing the user's unmodified C float_to_uint.
    # RS05 ranges also match the pinned official manual's C example.
    frame = encode_command(*values, spec=spec)
    assert frame.arbitration_id == identifier
    assert bytes(frame.data).hex() == payload


class FakeBus:
    """Replies become available only after their request, like an actual device."""

    def __init__(self, replies=(), *, pending=()):
        self.replies = iter(replies)
        self.incoming = list(pending)
        self.sent = []
        self.events = []
        self.closed = False

    def send(self, message, timeout):
        self.sent.append(message)
        self.events.append(("tx", message))
        self.incoming.extend(next(self.replies, []))

    def recv(self, timeout):
        if not self.incoming:
            return None
        frame = self.incoming.pop(0)
        self.events.append(("rx", frame))
        return frame

    def shutdown(self):
        self.closed = True


def startup_replies():
    return [
        [status()],  # Stop.
        [status()],  # Disable periodic reporting.
        [status()],  # MODE write ACK.
        [parameter(0x7005, 0, "B")],
        [status()],  # Watchdog write ACK.
        [parameter(0x7028, 2000)],
        [status(mode=2)],  # Enable ACK.
    ]


def test_start_and_control_follow_serial_ack_order(monkeypatch, spec):
    bus = FakeBus(startup_replies() + [[status(mode=2)], [status()]])
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    observed = []
    with Motor(
        spec, on_frame=lambda direction, frame: observed.append((direction, frame))
    ) as motor:
        assert motor.start().mode == 2
        assert motor.command(2.2436695, 0, 5, 0.2, 0).communication_type == 2
    assert [f.arbitration_id for f in bus.sent] == [
        0x0400FF7F,
        0x1800FF7F,
        0x1200FF7F,
        0x1100FF7F,
        0x1200FF7F,
        0x1100FF7F,
        0x0300FF7F,
        0x017FFF7F,
        0x0400FF7F,
    ]
    assert [bytes(f.data).hex() for f in bus.sent] == [
        "0000000000000000",
        "0102030405060000",
        "0570000000000000",
        "0570000000000000",
        "28700000d0070000",
        "2870000000000000",
        "0000000000000000",
        "96d87fff028f0a3d",
        "0000000000000000",
    ]
    assert [direction for direction, _ in observed] == ["tx", "rx"] * 9
    assert observed == bus.events
    assert bus.closed


@pytest.mark.parametrize("missing_phase", range(7))
def test_missing_startup_ack_or_readback_prevents_later_steps(monkeypatch, spec, missing_phase):
    replies = startup_replies()[:missing_phase] + [[], [status()]]
    bus = FakeBus(replies)
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    with pytest.raises(TimeoutError, match="reply"):
        with Motor(spec) as motor:
            motor.start()
    expected = [4, 24, 18, 17, 18, 17, 3][: missing_phase + 1] + [4]
    assert [f.arbitration_id >> 24 for f in bus.sent] == expected
    assert bus.closed


@pytest.mark.parametrize("index,phase,wrong_value", [(0x7005, 3, 3), (0x7028, 5, 0)])
def test_readback_mismatch_prevents_enable(monkeypatch, spec, index, phase, wrong_value):
    replies = startup_replies()[:phase] + [[parameter(index, wrong_value)], [status()]]
    bus = FakeBus(replies)
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    with pytest.raises(RuntimeError, match="readback"):
        with Motor(spec) as motor:
            motor.start()
    assert 3 not in [f.arbitration_id >> 24 for f in bus.sent]
    assert bus.closed


@pytest.mark.parametrize(
    "reply,error", [(status(), "expected mode 2"), (status(mode=2, faults=1), "fault")]
)
def test_enable_rejects_wrong_mode_or_faults(monkeypatch, spec, reply, error):
    bus = FakeBus(startup_replies()[:6] + [[reply], [status()]])
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    with pytest.raises(RuntimeError, match=error):
        with Motor(spec) as motor:
            motor.start()
    assert [f.arbitration_id >> 24 for f in bus.sent][-2:] == [3, 4]
    assert bus.closed


def test_old_periodic_foreign_and_parameter_frames_cannot_acknowledge_state(monkeypatch, spec):
    old = status()
    valid = status()
    distractors = [
        status(kind=24),
        status(motor_id=1),
        status(host_id=253),
        parameter(0x7019, 3.05465, "f"),
    ]
    bus = FakeBus([distractors + [valid], [status()]], pending=[old])
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    with Motor(spec) as motor:
        assert motor.read_state().arbitration_id == valid.arbitration_id
        assert motor.discarded_frames == 1
    assert bus.events[0] == ("rx", old)
    assert len([event for event in bus.events if event[0] == "rx"]) == 7
    assert [f.arbitration_id >> 24 for f in bus.sent] == [2, 4]
    assert all(bytes(f.data) == bytes(8) for f in bus.sent)


@pytest.mark.parametrize("bad_frame", [status(), status(kind=24)])
def test_preexisting_reply_without_new_reply_times_out(monkeypatch, spec, bad_frame):
    bus = FakeBus([[], [status()]], pending=[bad_frame])
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    with pytest.raises(TimeoutError, match="type-2 reply"):
        with Motor(spec) as motor:
            motor.read_state()
    assert [f.arbitration_id >> 24 for f in bus.sent] == [2, 4]
    assert bus.closed


def test_parameter_reads_correlate_motor_host_index_and_status(monkeypatch, spec):
    index = 0x7019
    bus = FakeBus(
        [
            [
                parameter(index, 99, "f", motor_id=1),
                parameter(index, 99, "f", host_id=253),
                parameter(0x701A, 99, "f"),
                status(kind=24),
                parameter(index, 1.25, "f"),
            ],
            [parameter(index, 999, "f", rejected=True)],
            [],
        ]
    )
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    motor = Motor(spec)
    try:
        assert motor.read_parameter(index) == 1.25
        with pytest.raises(RuntimeError, match="rejected register"):
            motor.read_parameter(index)
        with pytest.raises(TimeoutError, match="register 0x7019"):
            motor.read_parameter(index)
        with pytest.raises(ValueError, match="Unsupported register format"):
            motor.read_parameter(index, "d")
    finally:
        motor.close()
    assert [f.arbitration_id for f in bus.sent] == [0x1100FF7F] * 3
    assert all(bytes(f.data).hex() == "1970000000000000" for f in bus.sent)


@pytest.mark.parametrize("format,value", [("f", 5.5), ("B", 3), ("I", 2000)])
def test_parameter_formats(monkeypatch, spec, format, value):
    bus = FakeBus([[parameter(0x700B, value, format)]])
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    motor = Motor(spec)
    try:
        assert motor.read_parameter(0x700B, format) == pytest.approx(value)
    finally:
        motor.close()


def test_read_position_uses_type2_not_register_or_periodic(monkeypatch, spec):
    bus = FakeBus([[status()]])
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    motor = Motor(spec)
    try:
        assert motor.read_position() == pytest.approx(2.2435536736095205)
    finally:
        motor.close()
    assert [f.arbitration_id for f in bus.sent] == [0x0200FF7F]
    assert bytes(bus.sent[0].data) == bytes(8)


def test_read_only_fault_frame_aborts_and_stops_without_masking_error(monkeypatch, spec):
    fault = can.Message(
        arbitration_id=0x15007FFF, is_extended_id=True, data=struct.pack("<II", 8, 0)
    )
    bus = FakeBus([[fault], []])  # Stop ACK also fails.
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    with pytest.raises(RuntimeError, match="device fault 0x00000008") as exc:
        with Motor(spec) as motor:
            motor.read_state()
    assert any("stop failed" in note for note in exc.value.__notes__)
    assert [f.arbitration_id >> 24 for f in bus.sent] == [2, 4]
    assert bus.closed


def test_drain_logging_error_does_not_prevent_stop_or_close(monkeypatch, spec):
    bus = FakeBus(pending=[status()])
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)

    def broken_log(direction, frame):
        if direction == "rx":
            raise OSError("log failed")

    with pytest.raises(LookupError, match="original") as exc:
        with Motor(spec, on_frame=broken_log):
            raise LookupError("original")
    assert [f.arbitration_id >> 24 for f in bus.sent] == [4]
    assert any("log failed" in note for note in exc.value.__notes__)
    assert bus.closed


def test_inspection_is_read_only_and_preserves_failures(monkeypatch, tmp_path):
    from motorfit.config import load_setup
    from motorfit.devices.robstride.diagnostics import REGISTERS, inspect

    config = load_setup(MODEL_DIR.parents[1] / "setups/rs05_pendulum.toml")
    replies = []
    for name, (index, format) in REGISTERS.items():
        replies.append(
            [parameter(index, 23.05 if name == "VBUS" else 0, format, rejected=name == "limit_cur")]
        )
    bus = FakeBus(replies)
    monkeypatch.setattr(can, "Bus", lambda **kwargs: bus)
    output = tmp_path / "snapshot.json"
    result = inspect(config, output)
    assert result["parameters"]["VBUS"]["value"] == pytest.approx(23.05)
    assert "error" in result["parameters"]["limit_cur"]
    assert json.loads(output.read_text()) == result
    assert len(result["frames"]) == 2 * len(REGISTERS)
    assert {frame.arbitration_id >> 24 for frame in bus.sent} == {17}
    assert bus.closed
    with pytest.raises(FileExistsError):
        inspect(config, output)

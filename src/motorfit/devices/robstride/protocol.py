"""RobStride extended-CAN codecs with model-specific physical ranges."""

import math
import struct
from dataclasses import dataclass

import can

from .models import MotorSpec


def _encode(value: float, low: float, high: float) -> int:
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{value!r} is not representable in [{low}, {high}]")
    return int((value - low) * 65535 / (high - low))


def _decode(value: int, low: float, high: float) -> float:
    return value * (high - low) / 65535 + low


def quantize(value: float, low: float, high: float) -> float:
    """Return the physical value represented by the command's 16-bit field."""
    return _decode(_encode(value, low, high), low, high)


def _message(kind: int, motor_id: int, data2: int, data: bytes) -> can.Message:
    struct.pack("<BH", motor_id, data2)
    return can.Message(
        arbitration_id=(kind << 24) | (data2 << 8) | motor_id,
        is_extended_id=True,
        data=data,
        check=True,
    )


def encode_command(
    position: float,
    velocity: float,
    kp: float,
    kd: float,
    torque: float,
    *,
    spec: MotorSpec,
    motor_id: int = 127,
) -> can.Message:
    """Encode the five RobStride motion-control fields without clipping."""
    data = struct.pack(
        ">HHHH",
        _encode(position, *spec.position),
        _encode(velocity, *spec.velocity),
        _encode(kp, *spec.kp),
        _encode(kd, *spec.kd),
    )
    return _message(1, motor_id, _encode(torque, *spec.torque), data)


@dataclass(frozen=True, slots=True)
class Feedback:
    position: float
    velocity: float
    torque: float
    temperature: float
    faults: int
    mode: int
    motor_id: int
    timestamp: float
    communication_type: int
    arbitration_id: int


def _matches(message: can.Message, motor_id: int, host_id: int) -> bool:
    return (
        message.is_extended_id
        and not message.is_error_frame
        and not message.is_remote_frame
        and message.dlc == 8
        and len(message.data) == 8
        and (message.arbitration_id & 0xFF) == host_id
        and ((message.arbitration_id >> 8) & 0xFF) == motor_id
    )


def decode_feedback(
    message: can.Message,
    *,
    spec: MotorSpec,
    motor_id: int = 127,
    host_id: int = 255,
) -> Feedback | None:
    """Decode addressed type-2 status replies, as in the official SDK.

    Type-24 periodic packets remain raw evidence, never transaction feedback.
    Field ranges and the 65535 formula follow the model's pinned manual C example.
    """
    identifier = message.arbitration_id
    if not _matches(message, motor_id, host_id) or identifier >> 24 != 2:
        return None
    position, velocity, torque, temperature = struct.unpack(">HHHH", message.data)
    return Feedback(
        position=_decode(position, *spec.position),
        velocity=_decode(velocity, *spec.velocity),
        torque=_decode(torque, *spec.torque),
        temperature=temperature / 10,
        faults=(identifier >> 16) & 0x3F,
        mode=(identifier >> 22) & 3,
        motor_id=motor_id,
        timestamp=message.timestamp,
        communication_type=2,
        arbitration_id=identifier,
    )

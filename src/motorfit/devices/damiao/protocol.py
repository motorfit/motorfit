"""Damiao MIT command and feedback codecs.

Commands use 16-bit position and 12-bit velocity, torque and gain fields.
Acquisition rejects unrepresentable commands instead of clipping them.
"""

import math
from dataclasses import dataclass

import can


def encode(value, low, high, bits):
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{value!r} is not representable in [{low}, {high}]")
    return int((value - low) * ((1 << bits) - 1) / (high - low))


def decode(value, low, high, bits):
    return value * (high - low) / ((1 << bits) - 1) + low


def quantize(value, low, high, bits=12):
    return decode(encode(value, low, high, bits), low, high, bits)


def message(identifier, data):
    return can.Message(arbitration_id=identifier, is_extended_id=False, data=data, check=True)


def encode_command(position, velocity, kp, kd, torque, *, spec, motor_id):
    p = encode(position, *spec.position, 16)
    v = encode(velocity, *spec.velocity, 12)
    k = encode(kp, *spec.kp, 12)
    d = encode(kd, *spec.kd, 12)
    t = encode(torque, *spec.torque, 12)
    return message(
        motor_id,
        bytes(
            (
                p >> 8,
                p & 255,
                v >> 4,
                (v & 15) << 4 | k >> 8,
                k & 255,
                d >> 4,
                (d & 15) << 4 | t >> 8,
                t & 255,
            )
        ),
    )


def addressed(frame, feedback_id):
    return (
        not frame.is_extended_id
        and not frame.is_error_frame
        and not frame.is_remote_frame
        and frame.dlc == 8
        and len(frame.data) == 8
        and frame.arbitration_id == feedback_id
    )


def is_register(data):
    # Use only known register IDs to distinguish multiplexed replies.
    return (
        data[1] <= 15
        and data[2] in (0x33, 0x55)
        and data[3] in {*range(37), *range(50, 57), *range(59, 66), 80, 81}
    )


@dataclass(frozen=True, slots=True)
class Feedback:
    position: float
    velocity: float
    torque: float
    temperature: float
    rotor_temperature: float
    faults: int
    mode: int  # Normalized: 0 disabled, 2 enabled; status_code retains the wire value.
    status_code: int
    motor_id: int
    timestamp: float
    communication_type: int  # 0 = Damiao MIT sensor reply (no type field on wire).
    arbitration_id: int


def decode_feedback(frame, *, spec, motor_id, feedback_id):
    if not addressed(frame, feedback_id) or is_register(frame.data):
        return None
    b = frame.data
    if b[0] & 15 != motor_id & 15:
        return None
    status = b[0] >> 4
    return Feedback(
        position=decode(b[1] << 8 | b[2], *spec.position, 16),
        velocity=decode(b[3] << 4 | b[4] >> 4, *spec.velocity, 12),
        torque=decode((b[4] & 15) << 8 | b[5], *spec.torque, 12),
        temperature=float(b[6]),
        rotor_temperature=float(b[7]),
        faults=0 if status in (0, 1) else status,
        mode=2 if status == 1 else 0,
        status_code=status,
        motor_id=motor_id,
        timestamp=frame.timestamp,
        communication_type=0,
        arbitration_id=frame.arbitration_id,
    )

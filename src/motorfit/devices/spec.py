"""Physical ranges supplied by a motor model configuration."""

import math
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class MotorSpec:
    name: str
    family: str
    position: tuple[float, float]
    velocity: tuple[float, float]
    torque: tuple[float, float]
    kp: tuple[float, float]
    kd: tuple[float, float]
    source: str = ""
    protocol: dict = field(default_factory=dict)

    @property
    def recorded_effort(self):
        return self.family in {"myactuator", "hightorque", "hexfellow"}

    @classmethod
    def from_dict(cls, data: dict) -> "MotorSpec":
        if data["family"] not in {"robstride", "damiao", "myactuator", "hightorque", "hexfellow"}:
            raise ValueError(f"Unsupported motor family: {data['family']!r}")
        for key in ("position", "velocity", "torque", "kp", "kd"):
            bounds = data[key]
            if (
                len(bounds) != 2
                or not all(math.isfinite(v) for v in bounds)
                or bounds[0] >= bounds[1]
            ):
                raise ValueError(f"Invalid {key} limits: {bounds!r}")
        if data["family"] == "damiao" and (
            list(data["kp"]) != [0, 500] or list(data["kd"]) != [0, 5]
        ):
            raise ValueError("Damiao MIT gain encoding requires kp=[0,500], kd=[0,5]")
        protocol = dict(data.get("protocol", {}))
        if data["family"] == "myactuator":
            for key in ("torque_constant_nm_per_a", "current_limit_a"):
                value = protocol.get(key, 0)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"MyActuator requires positive protocol.{key}")
            if protocol["current_limit_a"] > 327.67:
                raise ValueError("MyActuator current limit exceeds int16 encoding")
        if data["family"] == "hexfellow" and protocol.get("firmware_version") not in (7, 8):
            raise ValueError("Hexfellow requires protocol.firmware_version = 7 or 8")
        return cls(
            name=data["name"],
            family=data["family"],
            **{key: tuple(data[key]) for key in ("position", "velocity", "torque", "kp", "kd")},
            source=data.get("source", ""),
            protocol=protocol,
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("position", "velocity", "torque", "kp", "kd"):
            data[key] = list(data[key])
        if not data["protocol"]:
            del data["protocol"]
        return data

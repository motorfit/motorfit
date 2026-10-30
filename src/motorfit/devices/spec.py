"""Physical ranges supplied by a motor model configuration."""

import math
from dataclasses import asdict, dataclass


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

    @classmethod
    def from_dict(cls, data: dict) -> "MotorSpec":
        if data["family"] not in {"robstride", "damiao"}:
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
        return cls(
            name=data["name"],
            family=data["family"],
            **{key: tuple(data[key]) for key in ("position", "velocity", "torque", "kp", "kd")},
            source=data.get("source", ""),
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("position", "velocity", "torque", "kp", "kd"):
            data[key] = list(data[key])
        return data

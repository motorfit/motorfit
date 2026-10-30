"""Native acquisition backends for supported controller protocols."""

from .spec import MotorSpec


def driver(family):
    if family == "robstride":
        from .robstride.motor import Motor
    elif family == "damiao":
        from .damiao.motor import Motor
    elif family in {"myactuator", "hightorque", "hexfellow"}:
        from importlib import import_module

        Motor = import_module(f"motor_identification.devices.{family}.motor").Motor
    else:
        raise ValueError(f"No BAM acquisition adapter for {family!r}; see motorfit motors")
    return Motor


def connection(config):
    device = config["device"]
    # host_id is retained for old RobStride setup files; Damiao uses feedback_id.
    feedback_id = device.get("feedback_id", device.get("host_id"))
    family = config["motor"]["family"]
    if feedback_id is None and family in {"myactuator", "hightorque", "hexfellow"}:
        feedback_id = {
            "myactuator": 0x240 + device["motor_id"],
            "hightorque": device["motor_id"],
            "hexfellow": 0x580 + device["motor_id"],
        }[family]
    if feedback_id is None:
        raise ValueError("Set device.feedback_id (or RobStride device.host_id)")
    return dict(
        spec=MotorSpec.from_dict(config["motor"]),
        channel=device["channel"],
        motor_id=device["motor_id"],
        host_id=feedback_id,
        timeout=device["timeout_s"],
    )


def command_value(spec, field, value):
    if spec.recorded_effort:
        import math

        low, high = getattr(spec, field)
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{field} outside configured limits")
        return value  # Host PD values; wire effort quantization is driver-specific.
    if spec.family == "damiao":
        from .damiao.protocol import quantize

        return quantize(value, *getattr(spec, field), bits=16 if field == "position" else 12)
    from .robstride.protocol import quantize

    return quantize(value, *getattr(spec, field))

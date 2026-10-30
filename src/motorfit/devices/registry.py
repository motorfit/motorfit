"""Native acquisition backends for supported controller protocols."""

from .spec import MotorSpec


def driver(family):
    if family == "robstride":
        from .robstride.motor import Motor
    elif family == "damiao":
        from .damiao.motor import Motor
    else:
        raise ValueError(f"No BAM acquisition adapter for {family!r}; see motorfit motors")
    return Motor


def connection(config):
    device = config["device"]
    # host_id is retained for old RobStride setup files; Damiao uses feedback_id.
    feedback_id = device.get("feedback_id", device.get("host_id"))
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
    if spec.family == "damiao":
        from .damiao.protocol import quantize

        return quantize(value, *getattr(spec, field), bits=16 if field == "position" else 12)
    from .robstride.protocol import quantize

    return quantize(value, *getattr(spec, field))

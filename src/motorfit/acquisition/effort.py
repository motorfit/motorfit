"""Host PD acquisition for current/torque protocols, with recorded BAM input."""

import json
import math
import time
from pathlib import Path

from motorfit.devices.registry import command_value, connection, driver
from motorfit.devices.spec import MotorSpec

from .trajectories import Trajectory


def record(config, output, *, motor_factory=None):
    spec = MotorSpec.from_dict(config["motor"])
    settings, device = config["recording"], config["device"]
    hz, zero = float(settings["hz"]), float(config["coordinate"]["zero_rad"])
    trajectory = Trajectory(settings)
    kp, kd = (command_value(spec, k, float(settings[k])) for k in ("kp", "kd"))
    if (
        not all(
            math.isfinite(x)
            for x in (hz, zero, trajectory.duration, trajectory.amplitude, trajectory.sweep_k)
        )
        or hz <= 0
        or trajectory.duration <= 0
    ):
        raise ValueError("Finite coordinates, trajectory and positive hz/duration are required")
    if settings.get("telemetry_hz", 0) != 0:
        raise ValueError("Set telemetry_hz=0; run inspect separately")
    if not spec.torque[0] <= 0 <= spec.torque[1]:
        raise ValueError("Experiment torque limits must include zero")
    period = 1 / hz
    watchdog = device["watchdog_ms"]
    if watchdog and period >= watchdog / 1000:
        raise ValueError("Recording interval must be shorter than the device watchdog")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    origin = time.monotonic()
    data = dict(
        motor=spec.name,
        motor_spec=spec.to_dict(),
        **config["fixture"],
        kp=kp,
        kd=kd,
        trajectory=trajectory.name,
        trajectory_parameters=trajectory.metadata,
        coordinate=config["coordinate"],
        config=config,
        completed=False,
        error=None,
        entries=[],
        control_source="recorded_effort",
        control_unit="nominal_Nm",
        control_policy="host PD from measured state; quantized effort held until next TX",
        feedback_policy="addressed serial transactions; multi-register state is not atomic",
        enable_state_source="reported CiA402 status"
        if spec.family == "hexfellow"
        else "commanded; protocol has no enable feedback",
        load_unit="nominal_Nm",
        input_volts_source="configured_supply",
        recording_origin_monotonic=origin,
    )
    motor, failure = None, None
    with (
        (output / "frames.jsonl").open("x") as frames,
        (output / "samples.jsonl").open("x") as samples,
    ):

        def on_frame(direction, frame):
            frames.write(
                json.dumps(
                    dict(
                        timestamp=time.monotonic() - origin,
                        bus_timestamp=frame.timestamp,
                        direction=direction,
                        arbitration_id=frame.arbitration_id,
                        is_extended_id=frame.is_extended_id,
                        is_fd=frame.is_fd,
                        bitrate_switch=frame.bitrate_switch,
                        is_error_frame=frame.is_error_frame,
                        is_remote_frame=frame.is_remote_frame,
                        dlc=frame.dlc,
                        data=bytes(frame.data).hex(),
                    )
                )
                + "\n"
            )
            frames.flush()

        try:
            factory = motor_factory or driver(spec.family)
            motor = factory(**connection(config), on_frame=on_frame)
            active = trajectory(0)[1]
            if active:
                motor.start(watchdog_ms=watchdog)
            else:
                motor.prepare()
            start = time.monotonic()
            data["control_origin_monotonic"] = start
            data["device_info"] = motor.info
            first_sample = None
            tick = 0
            while time.monotonic() < start + trajectory.duration:
                state_start = time.monotonic()
                feedback = motor.read_state()
                sampled = time.monotonic()
                if first_sample is None:
                    first_sample = sampled
                    data["first_feedback_monotonic"] = sampled
                position = feedback.position - zero
                # Hexfellow reports single-turn rev. The bench works within a
                # single swing around its saved downward coordinate.
                if spec.family == "hexfellow":
                    position = math.remainder(position, math.tau)
                if not all(
                    math.isfinite(x) for x in (position, feedback.velocity, feedback.torque)
                ):
                    raise RuntimeError("Nonfinite sensor feedback")
                if not spec.position[0] <= position <= spec.position[1]:
                    raise RuntimeError("Measured angle outside experiment limits")
                if not spec.velocity[0] <= feedback.velocity <= spec.velocity[1]:
                    raise RuntimeError("Measured speed outside experiment limits")
                if feedback.mode >= 0 and feedback.mode != (2 if active else 0):
                    raise RuntimeError("Drive enable state differs from commanded state")
                target, enabled = trajectory(sampled - start)
                command_value(spec, "position", target)
                transition_time = time.monotonic()
                if enabled != active:
                    if enabled:
                        motor.start(watchdog_ms=watchdog)
                    else:
                        motor.stop()
                    active = enabled
                requested = kp * (target - position) - kd * feedback.velocity if active else 0.0
                limited = max(spec.torque[0], min(spec.torque[1], requested))
                commanded = time.monotonic() if active else transition_time
                control = motor.command_torque(limited) if active else 0.0
                entry = dict(
                    timestamp=sampled - first_sample,
                    monotonic_time=sampled,
                    state_read_start_monotonic=state_start,
                    command_monotonic_time=commanded,
                    command_completed_monotonic=time.monotonic(),
                    transaction_id=len(data["entries"]) + 1,
                    bus_timestamp=feedback.timestamp,
                    feedback_arbitration_id=feedback.arbitration_id,
                    position=position,
                    speed=feedback.velocity,
                    load=feedback.torque,
                    goal_position=target,
                    input_volts=config["fixture"]["vin"],
                    torque_enable=active,
                    mode=feedback.mode,
                    faults=feedback.faults,
                    control=control,
                    requested_control=requested,
                )
                for key in ("temperature", "current", "statusword"):
                    value = getattr(feedback, key)
                    if value is not None:
                        entry[key] = value
                data["entries"].append(entry)
                samples.write(json.dumps(entry) + "\n")
                samples.flush()
                tick = max(tick + 1, int((time.monotonic() - start) / period) + 1)
                remaining = (
                    min(start + tick * period, start + trajectory.duration) - time.monotonic()
                )
                if remaining > 0:
                    time.sleep(remaining)
            if len(data["entries"]) < 2:
                raise TimeoutError("Recording needs at least two complete state/command cycles")
            data["completed"] = True
        except BaseException as exc:
            failure = exc
            data["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                if motor is not None:
                    try:
                        motor.stop()
                    finally:
                        motor.close()
            except BaseException as exc:
                data["completed"] = False
                data["cleanup_error"] = f"{type(exc).__name__}: {exc}"
                if failure is None:
                    data["error"] = data["cleanup_error"]
                    raise
            finally:
                data["finished_monotonic"] = time.monotonic()
                (output / "raw.json").write_text(json.dumps(data, indent=2) + "\n")
    return output / "raw.json"

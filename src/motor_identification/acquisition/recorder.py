"""Record fixed-gain MIT trajectories with incremental, unfiltered CAN evidence."""

import json
import math
import time
from pathlib import Path

from motor_identification.devices.registry import command_value, connection, driver
from motor_identification.devices.spec import MotorSpec

from .trajectories import Trajectory


def record(config: dict, output: Path, *, motor_factory=None) -> Path:
    spec = MotorSpec.from_dict(config["motor"])
    if spec.recorded_effort:
        from .effort import record as record_effort

        return record_effort(config, output, motor_factory=motor_factory)
    motor_factory = motor_factory or driver(spec.family)
    device, recording = config["device"], config["recording"]
    zero = float(config["coordinate"]["zero_rad"])
    kp, kd = float(recording["kp"]), float(recording["kd"])
    hz = float(recording["hz"])
    if not math.isfinite(hz) or hz <= 0:
        raise ValueError("Recording hz must be positive and finite")
    if float(recording.get("telemetry_hz", 0.0)) != 0:
        raise ValueError(
            "In-loop telemetry is not supported; use inspect before/after recording "
            "and set telemetry_hz=0"
        )
    period = 1.0 / hz
    trajectory = Trajectory(recording)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "raw.json"
    entries = []
    origin = time.monotonic()
    data = {
        "motor": spec.name,
        "motor_spec": spec.to_dict(),
        **config["fixture"],
        # Preserve requested gains for experiment grouping / BAM hold-out selection.
        # The model uses the values actually represented by the command fields.
        "kp": kp,
        "kd": kd,
        "kp_encoded": command_value(spec, "kp", kp),
        "kd_encoded": command_value(spec, "kd", kd),
        "goal_speed": command_value(spec, "velocity", 0.0),
        "feedforward_torque": command_value(spec, "torque", 0.0),
        "trajectory": trajectory.name,
        "trajectory_parameters": trajectory.metadata,
        "coordinate": config["coordinate"],
        "config": config,
        "recording_origin_monotonic": origin,
        "completed": False,
        "error": None,
        "entries": entries,
        "feedback_policy": (
            "type-2 serial request/reply; no periodic or telemetry stream"
            if spec.family == "robstride"
            else "Damiao addressed serial request/reply; queue drained before TX"
        ),
        "feedback_mode_encoding": "normalized: 0 disabled, 2 enabled",
        "load_unit": "nominal_Nm",
        "telemetry_file": None,
        "input_volts_source": "configured_supply",
    }
    motor = None
    failure = None
    with (
        (output / "frames.jsonl").open("x") as frames,
        (output / "samples.jsonl").open("x") as samples,
    ):

        def on_frame(direction, message):
            frames.write(
                json.dumps(
                    {
                        "timestamp": time.monotonic() - origin,
                        "bus_timestamp": message.timestamp,
                        "direction": direction,
                        "arbitration_id": message.arbitration_id,
                        "is_extended_id": message.is_extended_id,
                        "is_error_frame": message.is_error_frame,
                        "is_remote_frame": message.is_remote_frame,
                        "dlc": message.dlc,
                        "data": bytes(message.data).hex(),
                    }
                )
                + "\n"
            )
            frames.flush()

        try:
            motor = motor_factory(
                **connection(config),
                on_frame=on_frame,
            )
            active = trajectory(0.0)[1]
            if active:
                motor.start(watchdog_ms=device["watchdog_ms"])
            else:
                motor.prepare()
            start = time.monotonic()
            data["control_origin_monotonic"] = start
            first_feedback = None
            goal = zero
            command_time = start
            transaction_id = 0

            def save_feedback(feedback):
                nonlocal first_feedback
                expected_type = 2 if spec.family == "robstride" else 0
                if feedback.communication_type != expected_type:
                    raise RuntimeError("Acquisition requires a matching sensor transaction reply")
                received = time.monotonic()
                if first_feedback is None:
                    first_feedback = received
                    data["first_feedback_monotonic"] = received
                entry = {
                    "timestamp": received - first_feedback,
                    "monotonic_time": received,
                    "bus_timestamp": feedback.timestamp,
                    "command_monotonic_time": command_time,
                    "transaction_id": transaction_id,
                    "request_type": (1 if active else 2)
                    if spec.family == "robstride"
                    else (0 if active else 0xCC),
                    "feedback_type": feedback.communication_type,
                    "feedback_arbitration_id": feedback.arbitration_id,
                    "position": float(feedback.position) - zero,
                    "speed": float(feedback.velocity),
                    "load": float(feedback.torque),
                    "input_volts": float(config["fixture"]["vin"]),
                    "goal_position": command_value(spec, "position", goal) - zero,
                    "torque_enable": bool(feedback.mode == 2),
                    "temperature": float(feedback.temperature),
                    "faults": int(feedback.faults),
                    "mode": int(feedback.mode),
                }
                if spec.family == "damiao":
                    entry["status_code"] = feedback.status_code
                    entry["rotor_temperature"] = feedback.rotor_temperature
                entries.append(entry)
                samples.write(json.dumps(entry) + "\n")
                samples.flush()
                if feedback.faults:
                    raise RuntimeError(f"{spec.name} reported device faults: 0x{feedback.faults:x}")
                expected_mode = 2 if active else 0
                if feedback.mode != expected_mode:
                    raise RuntimeError(
                        f"{spec.name} replied in mode {feedback.mode}; expected mode {expected_mode}"
                    )

            tick = 0
            end = start + trajectory.duration
            while time.monotonic() < end:
                elapsed = time.monotonic() - start
                target, enabled = trajectory(elapsed)
                if enabled != active:
                    if enabled:
                        motor.start(watchdog_ms=device["watchdog_ms"])
                    else:
                        motor.stop()
                    active = enabled
                goal = zero + target
                command_time = time.monotonic()
                transaction_id += 1
                if active:
                    feedback = motor.command(goal, 0.0, kp, kd, 0.0)
                else:
                    feedback = motor.read_state()
                save_feedback(feedback)
                # Stay on the original clock grid; a late cycle does not create a burst.
                tick = max(tick + 1, int((time.monotonic() - start) / period) + 1)
                deadline = min(start + tick * period, end)
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
            if not entries:
                raise TimeoutError(f"No {spec.name} feedback received during recording")
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
                raw_path.write_text(json.dumps(data, indent=2) + "\n")
    return raw_path

"""Align recorded effort changes to their TX times, preserving held commands."""

from copy import deepcopy

import numpy as np


def resample_effort(data, dt):
    if not data.get("completed"):
        raise ValueError("Refusing to fit an incomplete effort recording")
    entries = data["entries"]
    if len(entries) < 2:
        raise ValueError("At least two samples are required")
    timestamps = np.array([e["timestamp"] for e in entries], dtype=float)
    commands = np.array([e["command_monotonic_time"] for e in entries])
    commands -= data["first_feedback_monotonic"]
    controls = np.array([e["control"] for e in entries])
    if (
        not np.isfinite(timestamps).all()
        or not np.isfinite(commands).all()
        or not np.isfinite(controls).all()
        or np.any(np.diff(timestamps) <= 0)
        or np.any(np.diff(commands) <= 0)
        or timestamps[0] != 0
        or np.any(commands < timestamps)
    ):
        raise ValueError("Invalid sample/command timeline or nonfinite effort")
    grid = np.arange(0, timestamps[-1], dt)
    result = deepcopy(data)
    result.update(dt=dt, entries=[], resampling="linear sensors; ZOH effort at command TX times")
    for t in grid:
        sensor_index = min(np.searchsorted(timestamps, t, side="right") - 1, len(entries) - 2)
        a, b = entries[sensor_index : sensor_index + 2]
        fraction = (t - timestamps[sensor_index]) / (
            timestamps[sensor_index + 1] - timestamps[sensor_index]
        )
        entry = {
            k: a[k] + (b[k] - a[k]) * fraction for k in ("position", "speed", "load", "input_volts")
        }
        for k in ("temperature", "current"):
            if k in a and k in b:
                entry[k] = a[k] + (b[k] - a[k]) * fraction
        command_index = np.searchsorted(commands, t, side="right") - 1
        # Startup commands are explicitly zero; don't backdate the first nonzero TX.
        command = entries[command_index] if command_index >= 0 else entries[0]
        entry.update(
            timestamp=float(t),
            control=float(controls[command_index]) if command_index >= 0 else 0.0,
            goal_position=command["goal_position"],
            torque_enable=bool(command["torque_enable"]),
        )
        result["entries"].append(entry)
    return result

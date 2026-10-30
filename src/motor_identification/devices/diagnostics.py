"""Read-only diagnostics for independent effort drivers."""

import json
import time
from dataclasses import asdict
from pathlib import Path

from .registry import connection, driver


def inspect(config, output, *, motor_factory=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(
        motor=config["motor"],
        device=config["device"],
        operations="read commands only; no enable, stop, zero or parameter write",
        parameters={},
        frames=[],
    )

    def on_frame(direction, frame):
        result["frames"].append(
            dict(
                time=time.time(),
                direction=direction,
                arbitration_id=frame.arbitration_id,
                is_extended_id=frame.is_extended_id,
                is_fd=frame.is_fd,
                data=bytes(frame.data).hex(),
            )
        )

    with output.open("x") as stream:
        factory = motor_factory or driver(config["motor"]["family"])
        motor = factory(**connection(config), on_frame=on_frame)
        try:
            result["parameters"] = motor.inspect()
            result["state"] = asdict(motor.read_state())
        except BaseException as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                motor.close()
            finally:
                json.dump(result, stream, indent=2)
                stream.write("\n")
    return result

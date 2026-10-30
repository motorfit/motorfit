"""Read-only Damiao register inspection with unfiltered wire evidence."""

import json
import time
from pathlib import Path

from ..registry import connection
from .motor import Motor

REGISTERS = {
    "MST_ID": (7, "I"),
    "ESC_ID": (8, "I"),
    "TIMEOUT": (9, "I"),
    "CTRL_MODE": (10, "I"),
    "PMAX": (21, "f"),
    "VMAX": (22, "f"),
    "TMAX": (23, "f"),
    "Rs": (17, "f"),
    "Ls": (18, "f"),
    "Gr": (20, "f"),
    "VBus": (60, "f"),
}


def inspect(config, output, *, motor_factory=Motor):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(
        motor=config["motor"],
        device=config["device"],
        operations="Damiao 0x33 register reads only",
        parameters={},
        frames=[],
    )

    def on_frame(direction, frame):
        result["frames"].append(
            dict(
                time=time.time(),
                bus_timestamp=frame.timestamp,
                direction=direction,
                id=hex(frame.arbitration_id),
                data=bytes(frame.data).hex(),
            )
        )

    with output.open("x") as stream:
        motor = motor_factory(**connection(config), on_frame=on_frame)
        try:
            for name, (index, format) in REGISTERS.items():
                item = {"index": index}
                try:
                    item["value"] = motor.read_parameter(index, format)
                except (RuntimeError, TimeoutError) as error:
                    item["error"] = str(error)
                result["parameters"][name] = item
        finally:
            try:
                motor.close()
            finally:
                json.dump(result, stream, indent=2)
                stream.write("\n")
    return result

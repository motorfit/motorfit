"""Documented scalar register snapshots using read commands only."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .models import MotorSpec
from .motor import Motor

# RS-series type-17 parameter table. Extended GUI indexes are a different
# interface and are deliberately not assumed to work through type 17.
REGISTERS = {
    "run_mode": (0x7005, "B"),
    "limit_torque": (0x700B, "f"),
    "limit_cur": (0x7018, "f"),
    "cur_kp": (0x7010, "f"),
    "cur_ki": (0x7011, "f"),
    "cur_filt_gain": (0x7014, "f"),
    "VBUS": (0x701C, "f"),
    "iqf": (0x701A, "f"),
    "mechPos": (0x7019, "f"),
    "mechVel": (0x701B, "f"),
    "canTimeout": (0x7028, "I"),
    "zero_sta": (0x7029, "B"),
}


def inspect(config: dict, output: Path, *, motor_factory=Motor) -> dict:
    """Save values, read failures and wire evidence without changing device state."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    device = config["device"]
    result = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "motor": config["motor"],
        "device": device,
        "operations": "type-17 parameter reads only",
        "parameters": {},
        "frames": [],
    }

    def on_frame(direction, message):
        result["frames"].append(
            {
                "time": time.time(),
                "bus_timestamp": message.timestamp,
                "direction": direction,
                "id": hex(message.arbitration_id),
                "data": bytes(message.data).hex(),
            }
        )

    # The normal Motor context manager stops on exit. Inspection only closes
    # its socket, so it cannot stop a device controlled by another process.
    with output.open("x") as stream:
        motor = motor_factory(
            MotorSpec.from_dict(config["motor"]),
            channel=device["channel"],
            motor_id=device["motor_id"],
            host_id=device["host_id"],
            timeout=device["timeout_s"],
            on_frame=on_frame,
        )
        try:
            for name, (index, data_format) in REGISTERS.items():
                item = {"index": hex(index)}
                try:
                    item["value"] = motor.read_parameter(index, data_format)
                except (TimeoutError, RuntimeError) as error:
                    item["error"] = str(error)
                result["parameters"][name] = item
        finally:
            try:
                motor.close()
            finally:
                json.dump(result, stream, indent=2)
                stream.write("\n")
    return result

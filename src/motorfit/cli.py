"""Command routing for acquisition and upstream BAM identification."""

import argparse
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .config import load_setup, save_zero


def main(argv: list[str] | None = None) -> None:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == "motors":
        from .devices.catalog import list_motors

        list_motors(arguments[1:])
        return
    if arguments and arguments[0] in {
        "demo",
        "verify",
        "replay",
        "release-replay",
        "audit-feedback",
        "export-formal",
    }:
        from importlib import import_module

        modules = {
            "demo": "offline",
            "verify": "validation.verify",
            "replay": "identification.validate_simulation",
            "release-replay": "validation.release",
            "audit-feedback": "validation.feedback",
            "export-formal": "acquisition.export_formal",
        }
        import_module(f"motorfit.{modules[arguments[0]]}").main(arguments[1:])
        return
    if arguments and arguments[0] in {"fit", "plot", "jitter"}:
        from .identification.bam.runner import bam_tool

        bam_tool(arguments[0], arguments[1:])
        return

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("read", "read feedback without enabling the motor"),
        ("inspect", "save device parameters using read commands only"),
        ("off", "disable the motor"),
        ("zero", "save the current known physical angle as a software coordinate"),
        ("record", "record one trajectory"),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--setup", type=Path, required=True)
        if name == "inspect":
            sub.add_argument("--out", type=Path, required=True)
        if name == "zero":
            sub.add_argument(
                "--angle",
                type=float,
                required=True,
                help="physical angle in rad; 0 = pendulum down",
            )
        if name == "record":
            sub.add_argument("--out", type=Path)
            sub.add_argument("--trajectory")
            for option in ("kp", "kd", "hz", "amplitude", "sweep-k", "telemetry-hz"):
                sub.add_argument(f"--{option}", type=float)
            sub.add_argument("--duration", type=float, dest="duration_s")
    sub = commands.add_parser("process", help="run BAM resampling")
    sub.add_argument("--raw", type=Path, required=True)
    sub.add_argument("--out", type=Path, required=True)
    sub.add_argument("--dt", type=float, default=0.005)
    for name in ("fit", "plot", "jitter"):
        commands.add_parser(name, help=f"forward arguments to bam.{name}")
    for name in ("demo", "verify", "replay", "release-replay", "audit-feedback", "export-formal"):
        commands.add_parser(name, help=f"{name} --help for portable dataset tools")
    commands.add_parser("motors", help="list motor families, models and integration levels")
    args = parser.parse_args(arguments)
    if args.command == "process":
        from .identification.bam.runner import process

        process(args.raw, args.out, args.dt)
        return

    config = load_setup(args.setup)
    if args.command == "inspect":
        from importlib import import_module

        from .devices.registry import driver

        driver(config["motor"]["family"])  # Validate before dynamic import or opening hardware.
        family = config["motor"]["family"]
        module = (
            "motorfit.devices.diagnostics"
            if family in {"myactuator", "hightorque", "hexfellow"}
            else f"motorfit.devices.{family}.diagnostics"
        )
        inspect = import_module(module).inspect
        result = inspect(config, args.out)
        print(json.dumps(result["parameters"], indent=2))
        print(f"Saved parameter and CAN evidence: {args.out}")
        return
    if args.command == "record":
        from .acquisition.recorder import record

        settings = config["recording"]
        for key in (
            "trajectory",
            "kp",
            "kd",
            "hz",
            "amplitude",
            "sweep_k",
            "duration_s",
            "telemetry_hz",
        ):
            value = getattr(args, key)
            if value is not None:
                settings[key] = value
        if "zero_rad" not in config["coordinate"]:
            parser.error("Set the physical coordinate first: zero --setup <file> --angle <rad>")
        for key in ("hz", "duration_s"):
            if not math.isfinite(settings[key]) or settings[key] <= 0:
                parser.error(f"{key} must be positive and finite")
        telemetry_hz = settings.get("telemetry_hz", 0.0)
        if telemetry_hz != 0:
            parser.error("Use telemetry_hz=0; run inspect separately before/after recording")
        output = args.out or Path("data/raw") / config["motor"]["name"] / str(time.time_ns())
        print(
            f"Recording {config['motor']['name']} / {settings['trajectory']}: "
            f"{settings['duration_s']} s, Kp={settings['kp']}, Kd={settings['kd']}, "
            f"{settings['hz']} Hz -> {output}",
            flush=True,
        )
        print(record(config, output))
        return

    from .devices.registry import connection, driver

    if args.command == "zero" and not math.isfinite(args.angle):
        parser.error("angle must be finite")
    with driver(config["motor"]["family"])(**connection(config)) as motor:
        if args.command == "off":
            motor.stop()
        elif args.command == "read":
            print(json.dumps(asdict(motor.read_state()), indent=2))
        elif args.command == "zero":
            raw = motor.read_position()
            path = Path(config["coordinate_file"])
            save_zero(path, raw - args.angle, config["coordinate"]["convention"])
            print(f"Encoder {raw:.9f} rad = physical {args.angle:.9f} rad; saved {path}")

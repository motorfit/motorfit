"""Reconstruct BAM sample entries from the formal C++ wire capture, offline."""

import argparse
import csv
import json
import struct
from pathlib import Path

from motorfit.dataset import save_json, sha256


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def decode(word, lo, hi):
    lo, hi = f32(lo), f32(hi)
    return f32(f32(f32(f32(hi - lo) * word) / 65535) + lo)


def table(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def reconstruct(record):
    """Recorded wire gains/targets are used, including float32 quantization."""
    record = Path(record)
    result = json.loads((record / "result.json").read_text())
    if not (
        result["trajectory_complete"]
        and result["stopped_verified"]
        and result["watchdog_restored"]
        and not result["error"]
        and not result["cleanup_error"]
    ):
        raise ValueError("Recording did not complete and stop successfully")
    samples, frames = table(record / "samples.csv"), table(record / "frames.csv")
    commands = [
        f for f in frames if f["direction"] == "tx" and f["phase"] in ("motion", "released")
    ]
    if len(commands) != len(samples):
        raise ValueError("Command and feedback sample counts differ")
    zero = result["fixed_zero_rad"]
    t0, last_goal, entries = int(samples[0]["host_monotonic_ns"]), None, []
    kpword = kdword = None
    for sample, command in zip(samples, commands, strict=True):
        cid = int(command["arbitration_id_hex"], 16)
        active = bool(int(sample["torque_enable"]))
        if active:
            q, _, kpword, kdword = struct.unpack(">4H", bytes.fromhex(command["data_hex"]))
            last_goal = decode(q, -12.57, 12.57) - zero
        if last_goal is None:
            raise ValueError("Missing initial active target")
        entry = dict(
            timestamp=(int(sample["host_monotonic_ns"]) - t0) / 1e9,
            monotonic_time=int(sample["host_monotonic_ns"]) / 1e9,
            command_monotonic_time=int(command["host_monotonic_ns"]) / 1e9,
            transaction_id=int(sample["sample"]),
            request_type=cid >> 24,
            feedback_type=2,
            feedback_arbitration_id=int(sample["arbitration_id_hex"], 16),
            position=float(sample["position_rad"]) - zero,
            speed=float(sample["velocity_rad_s"]),
            load=float(sample["torque_nm"]),
            input_volts=result["initial_voltage_v"],
            goal_position=last_goal,
            requested_goal_position=float(sample["target_rad"]) - zero,
            torque_enable=active,
            temperature=float(sample["temperature_c"]),
            faults=(int(sample["arbitration_id_hex"], 16) >> 16) & 63,
            mode=int(sample["mode"]),
            stage=int(sample["stage"]),
            hold=bool(int(sample["hold"])),
        )
        if entry["faults"] or entry["mode"] != (2 if active else 0):
            raise ValueError("Recorded fault or unexpected active/disabled state")
        entries.append(entry)
    return entries, {
        "kp_encoded": decode(kpword, 0, 500),
        "kd_encoded": decode(kdword, 0, 5),
        "goal_speed": decode(32767, -50, 50),
        "feedforward_torque": decode(32767, -5.5, 5.5),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="BAM metadata JSON (or an original raw.json used as metadata)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    metadata = json.loads(args.metadata.read_text())
    required = (
        "motor",
        "motor_spec",
        "motor_uid",
        "mass",
        "arm_mass",
        "length",
        "coordinate",
        "trajectory",
        "split",
        "kp",
        "kd",
    )
    if any(k not in metadata for k in required):
        parser.error(f"Metadata must contain {required}")
    entries, encoded = reconstruct(args.record)
    metadata.update(encoded, entries=entries)
    metadata["source_files"] = {
        p.name: {"path": p.name, "sha256": sha256(p)}
        for p in args.record.iterdir()
        if p.name
        in ("frames.csv", "samples.csv", "schedule.csv", "result.json", "independent.canlog")
    }
    save_json(args.output, metadata)
    print(f"Exported {len(entries)} recorded samples to {args.output}")

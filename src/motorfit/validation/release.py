"""Fixed-M1 release replay with an exact actuator event inside a physics step."""

import argparse
import ctypes
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np

from motorfit.dataset import Dataset, save_json, sha256
from motorfit.identification.mujoco import M1Parameters

from .feedback import capture_match, csv_read
from .metrics import scores

CASES = ("processed_enable", "stop_tx", "stop_ack1", "stop_ack2")


def build_library(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name("release_event.cpp")
    runtime = Path(mujoco.__file__).parent
    libraries = sorted(runtime.glob("libmujoco.so.*"))
    if sys.platform != "linux" or len(libraries) != 1:
        raise RuntimeError("Native release replay currently requires Linux and the MuJoCo wheel")
    target = directory / "release_event.so"
    if target.exists():
        raise FileExistsError(target)
    command = [
        "g++",
        "-std=c++17",
        "-O2",
        "-fPIC",
        "-shared",
        str(source),
        "-I" + str(runtime / "include"),
        str(libraries[0]),
        "-Wl,-rpath," + str(runtime),
        "-o",
        str(target),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    save_json(
        directory / "build.json",
        {"command": command, "source_sha256": sha256(source), "mujoco_version": mujoco.__version__},
    )
    lib = ctypes.CDLL(str(target))
    vec = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
    lib.rs05_release_event.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_double,
    ] + [vec] * 5
    lib.rs05_release_event.restype = ctypes.c_int
    return lib


def event_times(dataset, row):
    record = dataset.record_dir(row)
    log = dataset.log(row)
    frames, samples = csv_read(record / "frames.csv"), csv_read(record / "samples.csv")
    capture_match(frames, record / "independent.canlog")
    first_ns = int(samples[0]["host_monotonic_ns"])
    disabled = next(i for i, sample in enumerate(samples) if sample["torque_enable"] == "0")
    lower, upper = (
        int(samples[disabled - 1]["host_monotonic_ns"]),
        int(samples[disabled]["host_monotonic_ns"]),
    )
    stops = [
        f
        for f in frames
        if f["direction"] == "tx"
        and int(f["arbitration_id_hex"], 16) >> 24 == 4
        and lower < int(f["host_monotonic_ns"]) < upper
    ]
    if len(stops) != 1:
        raise ValueError("Expected one STOP between last active and first disabled sample")
    stop = stops[0]
    replies = [
        f
        for f in frames
        if f["direction"] == "rx"
        and int(stop["host_monotonic_ns"]) < int(f["host_monotonic_ns"]) < upper
    ]
    if len(replies) != 2 or any(int(f["arbitration_id_hex"], 16) != 0x02007FFD for f in replies):
        raise ValueError("Expected the two formal RS05 stopped-state acknowledgments")
    first_frame = next(
        f for f in frames if f["direction"] == "rx" and int(f["host_monotonic_ns"]) == first_ns
    )
    times = {
        "processed_enable": next(e["timestamp"] for e in log["entries"] if not e["torque_enable"])
    }
    for case, frame in zip(CASES[1:], [stop, *replies], strict=True):
        times[case] = (int(frame["host_monotonic_ns"]) - first_ns) / 1e9
        times[case + "_bus"] = (frame["bus_ns"] - first_frame["bus_ns"]) / 1e9
    return times


def replay(log, params, scene, dt, event, library):
    """No historic archive, stateful candidate model or existing binary is used."""
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("Physics timestep must be finite and positive")
    steps = round(log["dt"] / dt)
    if steps < 1 or not np.isclose(steps * dt, log["dt"]):
        raise ValueError("Physics timestep must divide the recording interval")
    xml = ET.fromstring(Path(scene).read_text())
    xml.find("option").set("timestep", str(dt))
    joint = xml.find(".//joint")
    expected = {
        "armature": params.armature,
        "damping": params.friction_viscous,
        "frictionloss": params.friction_base,
        "ref": -params.q_offset,
    }
    if any(float(joint.get(k)) != v for k, v in expected.items()):
        raise ValueError("Scene does not describe the frozen M1 parameters")
    model = mujoco.MjModel.from_xml_string(ET.tostring(xml, encoding="unicode"))
    if model.nv != 1 or model.opt.noslip_iterations != 1:
        raise ValueError("Expected the single-hinge release benchmark with NoSlip")
    data = mujoco.MjData(model)
    entries = log["entries"]
    data.qpos[0], data.qvel[0] = entries[0]["position"], entries[0]["speed"]
    mujoco.mj_forward(model, data)
    goals = np.repeat([e["goal_position"] for e in entries], steps)
    lag = params.command_delay / dt
    whole, fraction = int(np.floor(lag)), lag % 1
    ix = np.arange(len(goals))
    targets = np.ascontiguousarray(
        (1 - fraction) * goals[np.maximum(0, ix - whole)]
        + fraction * goals[np.maximum(0, ix - whole - 1)]
    )
    enabled = np.array([e["torque_enable"] for e in entries], dtype=float)
    p = np.array(
        [
            log.get("kp_encoded", log["kp"]),
            log.get("kd_encoded", log["kd"]),
            log.get("goal_speed", 0),
            log.get("feedforward_torque", 0),
            params.torque_ratio,
            params.torque_min,
            params.torque_max,
        ]
    )
    prediction, diagnostic = np.empty((len(entries), 5)), np.zeros(8)
    status = library.rs05_release_event(
        model._address,
        data._address,
        len(entries),
        steps,
        event,
        p,
        targets,
        enabled,
        prediction,
        diagnostic,
    )
    if status or not np.isfinite(prediction).all() or sum(w.number for w in data.warning):
        raise FloatingPointError("Non-finite or unstable release replay")
    if abs(diagnostic[0] - event) > 1e-10 or diagnostic[7] != 0 or model.opt.timestep != dt:
        raise ValueError("Release event gate failed")
    return prediction, diagnostic


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--scenes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record", nargs="+")
    parser.add_argument("--dt", type=float, default=0.0000625)
    parser.add_argument(
        "--cases", nargs="+", choices=(*CASES, *(c + "_bus" for c in CASES[1:])), default=CASES
    )
    args = parser.parse_args(argv)
    dataset = Dataset(args.dataset)
    rows = [
        r
        for r in dataset.rows
        if r["trajectory"] == "lift_and_drop" and (not args.record or r["id"] in args.record)
    ]
    if not rows:
        parser.error("No release recordings selected")
    args.output.mkdir(parents=True, exist_ok=False)
    library = build_library(args.output / "build")
    params = M1Parameters.load(dataset.model_path)
    metrics, events = [], {}
    for row in rows:
        log = dataset.log(row)
        events[row["id"]] = event_times(dataset, row)
        t = np.array([e["timestamp"] for e in log["entries"]])
        measured = np.array([[e["position"], e["speed"]] for e in log["entries"]])
        for case in args.cases:
            event = events[row["id"]][case]
            prediction, diagnostic = replay(
                log, params, args.scenes / f"{row['mass_g']}g.xml", args.dt, event, library
            )
            folder = args.output / case
            folder.mkdir(exist_ok=True)
            np.savez_compressed(
                folder / (row["id"] + ".npz"),
                prediction=prediction,
                measured=measured,
                timestamp=t,
                event_diagnostics=diagnostic,
                event_time_s=event,
            )
            metrics.append(
                {
                    "id": row["id"],
                    "mass_g": row["mass_g"],
                    "case": case,
                    "dt_s": args.dt,
                    "event_s": event,
                    **scores(prediction, measured, t, True),
                }
            )
    save_json(args.output / "events.json", events)
    save_json(args.output / "metrics.json", metrics)
    save_json(
        args.output / "protocol.json",
        {
            "model_sha256": sha256(dataset.model_path),
            "dataset_sha256": sha256(dataset.path),
            "mujoco_version": mujoco.__version__,
            "dt_s": args.dt,
            "scene_sha256": {
                str(g): sha256(args.scenes / f"{g}g.xml") for g in {r["mass_g"] for r in rows}
            },
            "parameters_refitted": False,
            "scope": "Sensitivity assumptions; STOP and reply times are not measured power-stage shutdown times.",
        },
    )
    print(json.dumps({"release_records": len(rows), "replays": len(metrics)}))


if __name__ == "__main__":
    main()

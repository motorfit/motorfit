"""Reproducible, frozen-parameter replay across optional physics backends.

Run in each backend's own environment with this repository's src on PYTHONPATH.
Existing fit artifacts and processed recordings are read-only inputs.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import numpy as np

from .mujoco import M1Parameters, PendulumReplay, pendulum_xml


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, allow_nan=False) + "\n")


def metrics(prediction, log, reference):
    entries = log["entries"]
    q = np.array([e["position"] for e in entries])
    v = np.array([e["speed"] for e in entries])
    t = np.arange(len(entries)) * log["dt"]
    error = prediction[:, 0] - q
    result = {
        "position_mae_rad": float(np.mean(abs(error))),
        "position_rmse_rad": float(np.sqrt(np.mean(error**2))),
        "position_max_abs_rad": float(np.max(abs(error))),
        "speed_mae_rad_s": float(np.mean(abs(prediction[:, 1] - v))),
        "bam_position_mae_rad": float(np.mean(abs(reference[:, 0] - q))),
        "delta_bam_position_mae_rad": float(np.mean(abs(prediction[:, 0] - reference[:, 0]))),
        "delta_bam_position_max_rad": float(np.max(abs(prediction[:, 0] - reference[:, 0]))),
        "samples": len(q),
    }
    if log["trajectory"] == "lift_and_drop":
        for name, mask in {
            "active": (t >= 2) & (t < 6),
            "release": (t >= 6) & (t < 8),
            "rest": t >= 8,
        }.items():
            result[name + "_mae_rad"] = float(np.mean(abs(error[mask])))
    return result


def summarize(records):
    result = {}
    for split in sorted({r["split"] for r in records}):
        rows = [r for r in records if r["split"] == split]
        result[split] = {"records": len(rows)}
        for key in (
            "position_mae_rad",
            "position_rmse_rad",
            "speed_mae_rad_s",
            "bam_position_mae_rad",
            "delta_bam_position_mae_rad",
        ):
            result[split][key] = float(np.mean([r[key] for r in rows]))
        worst = max(rows, key=lambda r: r["position_mae_rad"])
        result[split]["worst_record"] = worst["id"]
        result[split]["worst_record_mae_rad"] = worst["position_mae_rad"]
    return result


def load_records(manifest, splits=None):
    from motorfit.dataset import Dataset

    dataset = Dataset(manifest)
    loaded = []
    for row in dataset.rows:
        if splits and row["split"] not in splits:
            continue
        current = {**row, "processed_path": str(dataset.resolve(row["processed_path"]))}
        loaded.append((current, dataset.log(row), dataset.reference(row)))
    return loaded


def evaluate(
    manifest,
    output,
    engine,
    dt,
    ablations=False,
    scene_assets=None,
    fixture_model="finite",
    options=None,
    friction="original",
):
    output.mkdir(parents=True, exist_ok=False)
    from motorfit.dataset import Dataset

    dataset = Dataset(manifest)
    parameter_path = dataset.model_path
    params = M1Parameters.load(parameter_path)
    before = sha256(parameter_path)
    rows = load_records(manifest)
    xml_factory = pendulum_xml
    if scene_assets is not None:
        from motorfit.rigs.rs05_bench import bench_xml

        xml_factory = partial(bench_xml, assets=scene_assets, fixture_model=fixture_model)
    from motorfit.validation.options import configure

    base_factory = xml_factory
    option_text = None if options is None else Path(options).read_text()

    def xml_factory(log, parameters, timestep):
        return configure(base_factory(log, parameters, timestep), option_text, friction, timestep)

    for grams in sorted({row["mass_g"] for row, _, _ in rows}):
        log = next(log for row, log, _ in rows if row["mass_g"] == grams)
        path = output / "scenes" / f"rs05_{grams}g.xml"
        path.parent.mkdir(exist_ok=True)
        path.write_text(xml_factory(log, params, dt))
    versions = {}
    for package in ("numpy", "mujoco", "newton", "warp-lang", "mujoco-warp", "mjlab", "torch"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    protocol = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engine": engine,
        "physics_dt_s": dt,
        "params": asdict(params),
        "parameter_file": str(parameter_path),
        "parameter_sha256": before,
        "data_manifest_sha256": sha256(manifest),
        "versions": versions,
        "records": len(rows),
        "scene": "equivalent_pendulum" if scene_assets is None else "cad_bench",
        "scene_assets": None if scene_assets is None else str(scene_assets),
        "fixture_model": "identified_point" if scene_assets is None else fixture_model,
        "asset_manifest_sha256": None
        if scene_assets is None
        else sha256(scene_assets / "manifest.json"),
        "initialization": "Recorded q/v once; no periodic state resynchronization",
        "commands": "Recorded encoded gains; zero-order hold raw goal at log dt; causal fractional delay at physics dt; immediate enable",
        "friction": friction,
        "solver_option_xml": option_text,
        "acceptance": {
            "mean_position_mae_rad_per_split_max": 0.005,
            "parameter_refit": False,
            "robot_integration": False,
        },
    }
    save_json(output / "protocol.json", protocol)
    if engine == "mujoco":

        def rollout_batch(logs, parameters):
            return [
                PendulumReplay(log, parameters, dt, xml_factory=xml_factory).rollout()
                for log in logs
            ]
    elif engine == "newton":
        import mujoco

        from motorfit.validation.options import apply_options, option_values

        from .newton import NewtonPendulumBatch

        def rollout_batch(logs, parameters):
            reference = mujoco.MjModel.from_xml_string(xml_factory(logs[0], parameters, dt))
            integrator = "implicitfast" if int(reference.opt.integrator) == 3 else "euler"
            obj = NewtonPendulumBatch(
                logs, parameters, dt, xml_factory=xml_factory, integrator=integrator
            )
            expected = option_values(reference.opt)
            obj.model.gravity.assign(np.asarray([reference.opt.gravity], dtype=np.float32))
            apply_options(expected, obj.mj_model.opt)
            predictions = obj.rollout()
            if option_values(obj.mj_model.opt) != expected:
                raise ValueError("Newton solver options changed during replay")
            return predictions
    elif engine == "mjlab":
        from motorfit.validation.options import audit_gpu, gpu_batch, option_values

        from .mjlab import fixture_key

        def rollout_batch(logs, parameters):
            groups = {}
            for index, log in enumerate(logs):
                groups.setdefault(fixture_key(log), []).append(index)
            predictions = [None] * len(logs)
            for indices in groups.values():
                obj = gpu_batch([logs[i] for i in indices], parameters, xml_factory, dt)
                expected = option_values(obj.sim.mj_model.opt)
                audit_gpu(obj, expected)
                for i, prediction in zip(indices, obj.rollout(), strict=True):
                    predictions[i] = prediction
                audit_gpu(obj, expected)
            return predictions
    else:
        raise ValueError(engine)
    predictions = rollout_batch([log for _, log, _ in rows], params)
    records = []
    for (row, log, reference), prediction in zip(rows, predictions, strict=True):
        if prediction.shape != (len(log["entries"]), 5) or not np.all(np.isfinite(prediction)):
            raise ValueError(f"Invalid prediction: {row['id']}")
        disabled = np.array([not e["torque_enable"] for e in log["entries"]])
        if np.any(prediction[disabled, 3] != 0):
            raise ValueError(f"Nonzero motor torque when disabled: {row['id']}")
        record = {k: row[k] for k in ("id", "mass_g", "repeat", "trajectory", "kp", "kd", "split")}
        record.update(metrics(prediction, log, reference))
        records.append(record)
        folder = output / "predictions"
        folder.mkdir(exist_ok=True)
        np.savez_compressed(
            folder / (row["id"] + ".npz"),
            prediction=prediction,
            columns=["position", "speed", "nominal_torque", "motor_torque", "delayed_goal"],
            timestamp=np.array([e["timestamp"] for e in log["entries"]]),
            measured=np.array([[e["position"], e["speed"], e["load"]] for e in log["entries"]]),
            measured_columns=["position", "speed", "firmware_nominal_torque"],
            command=np.array([[e["goal_position"], e["torque_enable"]] for e in log["entries"]]),
            command_columns=["encoded_position_goal", "torque_enable"],
        )
    summary = summarize(records)
    save_json(output / "metrics.json", {"aggregate": summary, "records": records})
    with (output / "metrics.csv").open("w") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(dict.fromkeys(k for r in records for k in r))
        )
        writer.writeheader()
        writer.writerows(records)
    if ablations:
        training = [(r, log, ref) for r, log, ref in rows if r["split"] == "train"]
        cases = {
            "no_delay": replace(params, command_delay=0),
            "no_friction": replace(params, friction_base=0, friction_viscous=0),
            "no_armature": replace(params, armature=0),
        }
        ablation_rows = []
        for name, altered in cases.items():
            predicted = rollout_batch([log for _, log, _ in training], altered)
            for (row, log, ref), prediction in zip(training, predicted, strict=True):
                baseline = predictions[
                    next(i for i, (r, _, _) in enumerate(rows) if r["id"] == row["id"])
                ]
                ablation_rows.append(
                    {
                        "case": name,
                        "id": row["id"],
                        **metrics(prediction, log, ref),
                        "delta_full_m1_position_mae_rad": float(
                            np.mean(abs(prediction[:, 0] - baseline[:, 0]))
                        ),
                    }
                )
        save_json(output / "ablations.json", ablation_rows)
    if sha256(parameter_path) != before:
        raise ValueError("Parameter file changed during evaluation")
    for row, _, _ in rows:
        if sha256(row["processed_path"]) != row["sha256"]:
            raise ValueError("Source recording changed during evaluation")
    save_json(
        output / "COMPLETE.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "sources_unchanged": True,
            "trajectory_gate_pass": all(s["position_mae_rad"] <= 0.005 for s in summary.values()),
            "note": "Mechanism checks are separate; passing this error bound alone is insufficient.",
        },
    )
    print(json.dumps(summary, indent=2), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", choices=["mujoco", "newton", "mjlab"], required=True)
    parser.add_argument("--dt", type=float, default=0.002)
    parser.add_argument("--ablations", action="store_true")
    parser.add_argument("--scene-assets", type=Path)
    parser.add_argument("--fixture-model", choices=["finite", "identified_point"], default="finite")
    parser.add_argument(
        "--options", type=Path, help="MJCF option fragment; replaces all scene options"
    )
    parser.add_argument("--friction", choices=["original", "default"], default="original")
    args = parser.parse_args(argv)
    evaluate(
        args.dataset.resolve(),
        args.output.resolve(),
        args.engine,
        args.dt,
        args.ablations,
        None if args.scene_assets is None else args.scene_assets.resolve(),
        args.fixture_model,
        args.options,
        args.friction,
    )


if __name__ == "__main__":
    main()

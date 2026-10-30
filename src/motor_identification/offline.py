"""Small real-data example: frozen BAM replay and a headless comparison plot."""

import argparse
import csv
from pathlib import Path

import numpy as np
from bam.simulate import Simulator

from .dataset import Dataset, save_json, sha256
from .identification.bam import load_model


def run(manifest, output):
    dataset = Dataset(manifest)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    summary = dataset.verify()
    model = load_model(dataset.model_path)
    rows, traces = [], []
    for row in dataset.rows:
        log = dataset.log(row)
        positions, speeds, controls = Simulator(model).rollout_log(log, simulate_control=True)
        prediction = np.column_stack((positions, speeds))
        reference = dataset.reference(row)[:, :2]
        delta = float(np.max(abs(prediction - reference)))
        if not np.isfinite(prediction).all() or delta > 1e-10:
            raise ValueError(f"Frozen BAM reference regression: {row['id']} ({delta})")
        t = np.array([e["timestamp"] for e in log["entries"]])
        measured = np.array([e["position"] for e in log["entries"]])
        error = prediction[:, 0] - measured
        rows.append(
            {
                "id": row["id"],
                "split": row["split"],
                "mass_g": row["mass_g"],
                "position_mae_rad": float(np.mean(abs(error))),
                "position_rmse_rad": float(np.sqrt(np.mean(error**2))),
                "reference_max_abs_difference": delta,
            }
        )
        traces.append((row, t, measured, prediction[:, 0]))
        np.savez_compressed(
            output / f"{row['id']}.npz", timestamp=t, measured=measured, prediction=prediction
        )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(traces), 1, figsize=(10, 2.8 * len(traces)), squeeze=False)
    for ax, (row, t, measured, predicted) in zip(axes[:, 0], traces, strict=True):
        ax.plot(t, measured, color="#24344b", label="Measured", linewidth=1.5)
        ax.plot(t, predicted, color="#ec7c32", label="Frozen M1", linewidth=1)
        ax.set(
            title=f"{row['mass_g']} g / {row['trajectory']} / {row['split']}",
            xlabel="Time [s]",
            ylabel="Position [rad]",
        )
        ax.grid(alpha=0.2)
        ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(output / "comparison.png", dpi=160)
    plt.close(fig)
    with (output / "metrics.csv").open("w") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary.update(
        engine="Pinned Rhoban BAM",
        parameters_refitted=False,
        manifest_sha256=sha256(dataset.path),
        metrics=rows,
    )
    save_json(output / "summary.json", summary)
    print(f"PASS: {len(rows)} complete recordings; frozen references reproduced. {output}")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    run(args.dataset, args.output)


if __name__ == "__main__":
    main()

"""Render light/dark identification figures from one complete, hash-checked recording."""

import argparse
from pathlib import Path

import matplotlib
import numpy as np

from motorfit.dataset import Dataset

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RECORD = "100g_09_v3_100g_r01_sin_time_square_kp20_kd0.6"
PALETTES = {
    "light": {
        "background": "#FFFFFF",
        "ink": "#1F2328",
        "muted": "#59636E",
        "grid": "#D8DEE4",
        "measured": "#2563EB",
        "predicted": "#C75B12",
    },
    "dark": {
        "background": "#0D1117",
        "ink": "#F0F6FC",
        "muted": "#B1BAC4",
        "grid": "#30363D",
        "measured": "#79AEFF",
        "predicted": "#FFA86A",
    },
}


def render(output: Path, theme: str = "light") -> None:
    dataset = Dataset(ROOT / "tests/fixtures/offline/manifest.json")
    row = next(row for row in dataset.rows if row["id"] == RECORD)
    log = dataset.log(row)
    measured = np.array([entry["position"] for entry in log["entries"]])
    time = np.array([entry["timestamp"] for entry in log["entries"]])
    predicted = dataset.reference(row)[:, 0]
    if predicted.shape != measured.shape or not np.isfinite(predicted).all():
        raise ValueError("Invalid reference trace")
    # Use every sample; neither series is smoothed, fitted, shifted or rescaled.
    error_mrad = 1000 * (predicted - measured)
    rmse_mrad = float(np.sqrt(np.mean(error_mrad**2)))
    palette = PALETTES[theme]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "text.color": palette["ink"],
            "axes.labelcolor": palette["muted"],
            "xtick.color": palette["muted"],
            "ytick.color": palette["muted"],
            "axes.edgecolor": palette["grid"],
            "axes.linewidth": 0.7,
        }
    )
    fig = plt.figure(figsize=(11, 4.1), facecolor=palette["background"])
    fig.text(0.08, 0.94, "RS05 / 100 g", fontsize=14, weight="bold")
    angle = fig.add_axes((0.08, 0.46, 0.89, 0.36))
    residual = fig.add_axes((0.08, 0.18, 0.89, 0.16), sharex=angle)
    for ax in (angle, residual):
        ax.set_facecolor(palette["background"])
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color=palette["grid"], linewidth=0.7)
        ax.set_axisbelow(True)
        ax.tick_params(axis="both", length=3, width=0.7, pad=5, labelsize=10)
        ax.set_xlim(0, 20)
        ax.set_xticks([0, 5, 10, 15, 20])
    (measured_line,) = angle.plot(time, measured, color=palette["measured"], lw=2, label="Measured")
    (predicted_line,) = angle.plot(
        time, predicted, color=palette["predicted"], lw=1.7, ls=(0, (4, 2)), label="BAM M1"
    )
    angle.set_ylim(-0.30, 0.30)
    angle.set_yticks([-0.2, 0, 0.2])
    angle.set_ylabel("Angle (rad)", labelpad=10)
    angle.tick_params(labelbottom=False)
    fig.legend(
        handles=[measured_line, predicted_line],
        loc="upper right",
        bbox_to_anchor=(0.978, 1.005),
        frameon=False,
        ncol=2,
        fontsize=11,
        handlelength=2.5,
        columnspacing=1.7,
    )
    residual.axhline(0, color=palette["muted"], lw=0.7)
    residual.plot(time, error_mrad, color=palette["predicted"], lw=1.05)
    residual.set_ylim(-8, 8)
    residual.set_yticks([-8, 0, 8])
    residual.set_ylabel("Error (mrad)", labelpad=10)
    residual.set_xlabel("Elapsed time (s)", labelpad=4)
    fig.text(
        0.08,
        0.015,
        f"Full 20 s · {len(time):,} samples · error = prediction − measurement",
        fontsize=9,
        color=palette["muted"],
    )
    fig.text(
        0.97,
        0.015,
        f"Position RMSE {rmse_mrad:.2f} mrad",
        fontsize=9,
        color=palette["muted"],
        ha="right",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output,
        dpi=180,
        facecolor=palette["background"],
        metadata={
            "Description": (
                f"Record: {RECORD}; split: {row['split']}; all {len(time)} processed samples. "
                f"Model SHA-256: {dataset.metadata['model_sha256']}. "
                "Source: tests/fixtures/offline/manifest.json. Saved frozen BAM reference; no refitting."
            )
        },
    )
    plt.close(fig)
    print(f"{output}: {len(time)} samples; position RMSE {rmse_mrad:.6f} mrad")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=PALETTES, default="light")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    suffix = "-dark" if args.theme == "dark" else ""
    output = args.output or ROOT / f"docs/images/identification{suffix}.png"
    render(output, args.theme)

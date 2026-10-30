"""Full-length three-backend replay with measured reference curves on a black canvas."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from motor_identification.dataset import Dataset
from motor_identification.identification.mujoco import M1Parameters
from motor_identification.rigs.rs05_bench import bench_xml

WIDTH, HEIGHT, FPS = 1920, 1080, 30
COLUMN_W = WIDTH // 3
VIEW_W, VIEW_H = COLUMN_W - 16, 480
MEASURED = "#eeeeee"
COLORS = ("#4ddfcb", "#ffb75d", "#bda0ff")
NAMES = ("MuJoCo CPU", "Newton / SolverMuJoCo CPU", "mjlab / MuJoCo Warp GPU")
ENGINES = ("mujoco", "newton", "mjlab")
TITLES = {
    "sin_time_square": "Chirp",
    "sin_sin": "Composite sine",
    "up_and_down": "Up and down",
    "lift_and_drop": "Lift and drop",
    "long_sweep": "Long sweep",
}
FONTS = {}


def load_fonts(path=None):
    from matplotlib import font_manager

    font = path or font_manager.findfont("DejaVu Sans")
    return {s: ImageFont.truetype(str(font), s) for s in (18, 20, 22, 24, 28, 34, 40)}


BG = "#000000"
MUTED = "#90969d"
GRID = "#24272b"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(source, output, assets, row, dataset, preview=None):
    log = dataset.log(row)
    p = M1Parameters.load(dataset.model_path)
    es = log["entries"]
    t = np.array([e["timestamp"] for e in es])
    q = np.array([e["position"] for e in es])
    preds = [
        np.load(source / f"{engine}_finite/predictions" / f"{row['id']}.npz")["prediction"]
        for engine in ENGINES
    ]
    series = [x[:, :2] for x in preds]
    model = mujoco.MjModel.from_xml_string(bench_xml(log, p, 0.002, assets=assets))
    data = mujoco.MjData(model)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0, -0.01, 0.266]
    camera.distance = 0.53
    camera.azimuth = 110
    camera.elevation = -13
    model.vis.headlight.ambient[:] = 0.28
    model.vis.headlight.diffuse[:] = 0.45
    model.light_diffuse[0, :] = 0.6
    model.light_diffuse[1, :] = 0.2
    # tint only the moving beam and load; each panel's curve uses the same hue.
    tinted = [model.geom("beam").id, model.geom(f"weight_{row['mass_g']}g").id]
    duration = len(t) * log["dt"]
    frames = int(np.ceil(duration * FPS - 1e-9))
    base = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(base)
    d.text(
        (32, 22),
        f"RS05  /  {row['mass_g']} g  /  {TITLES[row['trajectory']]}",
        font=FONTS[34],
        fill="white",
    )
    d.line([(32, 92), (1888, 92)], fill=GRID, width=1)
    for k, name in enumerate(NAMES):
        x = k * COLUMN_W
        d.text((x + 28, 115), name, font=FONTS[28], fill=COLORS[k])
        if k:
            d.line([(x, 112), (x, 998)], fill=GRID, width=1)
    lo = min(float(q.min()), *(float(x[:, 0].min()) for x in series))
    hi = max(float(q.max()), *(float(x[:, 0].max()) for x in series))
    pad = max((hi - lo) * 0.12, 0.025)
    lo -= pad
    hi += pad
    # Same position and time scale for every column. No velocity/torque traces.
    y0, y1 = 750, 950
    d.text((32, 680), "Angle q / rad", font=FONTS[22], fill="white")
    d.line([(1240, 696), (1274, 696)], fill=MEASURED, width=2)
    d.text((1286, 680), "White: measured", font=FONTS[20], fill=MEASURED)
    d.line([(1485, 696), (1519, 696)], fill=COLORS[0], width=3)
    d.text((1531, 680), "Color: simulation", font=FONTS[20], fill=MUTED)
    bounds = []
    for k in range(len(ENGINES)):
        x0, x1 = k * COLUMN_W + 70, (k + 1) * COLUMN_W - 30
        bounds.append((x0, x1))
        for value in np.linspace(lo, hi, 3):
            y = y1 - (value - lo) / (hi - lo) * (y1 - y0)
            d.line([(x0, y), (x1, y)], fill=GRID, width=1)
            d.text((x0 - 12, y), f"{value:.2f}", font=FONTS[18], fill=MUTED, anchor="rm")
        for tick in np.linspace(0, duration, 5):
            x = x0 + tick / duration * (x1 - x0)
            d.line([(x, y0), (x, y1)], fill=GRID, width=1)
            d.text((x, 964), f"{tick:g}", font=FONTS[18], fill=MUTED, anchor="mt")
        d.text((x1, 1000), "t / s", font=FONTS[18], fill=MUTED, anchor="ra")
    d.text((32, 1032), "Error: simulated - measured", font=FONTS[20], fill=MUTED)
    file = output / f"rs05_{row['mass_g']}g_{row['trajectory']}_complete.mp4"
    process = None
    if preview is None:
        if file.exists():
            raise FileExistsError(file)
        process = subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-n",
                "-f",
                "rawvideo",
                "-pixel_format",
                "rgb24",
                "-video_size",
                f"{WIDTH}x{HEIGHT}",
                "-framerate",
                str(FPS),
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-threads",
                "2",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(file),
            ],
            stdin=subprocess.PIPE,
        )
    selected = [round(preview * FPS)] if preview is not None else range(frames)
    with mujoco.Renderer(model, height=VIEW_H, width=VIEW_W) as renderer:
        renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
        for f in selected:
            seconds = min(f / FPS, t[-1])
            idx = min(int(seconds / log["dt"]), len(t) - 1)
            im = base.copy()
            draw = ImageDraw.Draw(im)
            enabled = es[idx]["torque_enable"]
            stage = "Released" if not enabled else ("Holding" if es[idx]["hold"] else "Driving")
            draw.text(
                (1888, 26),
                f"{seconds:05.2f} / {duration:.2f} s",
                font=FONTS[28],
                fill="white",
                anchor="ra",
            )
            draw.text(
                (1888, 65),
                f"{stage}    ·    Original speed 1x",
                font=FONTS[18],
                fill=MUTED,
                anchor="ra",
            )
            measured = float(np.interp(seconds, t, q))
            for k, values in enumerate(series):
                simq = float(np.interp(seconds, t, values[:, 0]))
                simv = float(np.interp(seconds, t, values[:, 1]))
                rgb = tuple(int(COLORS[k][i : i + 2], 16) / 255 for i in (1, 3, 5))
                for gid in tinted:
                    model.geom_rgba[gid, :3] = rgb
                data.qpos[0] = simq
                data.qvel[0] = simv
                mujoco.mj_forward(model, data)
                renderer.update_scene(data, camera=camera)
                renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
                im.paste(Image.fromarray(renderer.render()), (k * COLUMN_W + 8, 194))
                draw.text(
                    ((k + 1) * COLUMN_W - 30, 635),
                    f"{simq:+.4f} rad",
                    font=FONTS[24],
                    fill=COLORS[k],
                    anchor="ra",
                )
                x0, x1 = bounds[k]
                last = idx + 1
                xx = x0 + t[:last] / duration * (x1 - x0)

                def line(y, color, width):
                    yy = y1 - (y[:last] - lo) / (hi - lo) * (y1 - y0)
                    if last > 1:
                        draw.line(list(zip(xx, yy)), fill=color, width=width)

                line(q, MEASURED, 2)
                line(values[:, 0], COLORS[k], 3)
                x = x0 + seconds / duration * (x1 - x0)
                y = y1 - (simq - lo) / (hi - lo) * (y1 - y0)
                draw.line([(x, y0), (x, y1)], fill="#62666b", width=1)
                draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=COLORS[k])
                draw.text(
                    ((k + 1) * COLUMN_W - 30, 1030),
                    f"Δq  {(simq - measured) * 1000:+.2f} mrad",
                    font=FONTS[22],
                    fill=COLORS[k],
                    anchor="ra",
                )
            if preview is not None:
                target = output / f"preview_{row['mass_g']}g_{row['trajectory']}_{preview:g}s.png"
                im.save(target)
                print(target, flush=True)
            else:
                if f == round(8 * FPS):
                    im.save(file.with_suffix(".png"))
                process.stdin.write(im.tobytes())
            if preview is None and f % 300 == 0:
                print(row["mass_g"], row["trajectory"], f, "/", frames, flush=True)
    if process:
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("ffmpeg failed")
        metadata = {
            "video": file.name,
            "record": row["id"],
            "frames": frames,
            "fps": FPS,
            "duration_s": frames / FPS,
            "source_duration_s": duration,
            "playback_speed": 1,
            "start_time_s": 0,
            "last_frame_time_s": (frames - 1) / FPS,
            "source_final_sample_time_s": float(t[-1]),
            "source_processed_sha256": sha(dataset.resolve(row["processed_path"])),
            "prediction_sha256": {
                e: sha(source / f"{e}_finite/predictions" / f"{row['id']}.npz") for e in ENGINES
            },
            "panels": dict(zip(NAMES, ENGINES, strict=True)),
            "panel_colors": dict(zip(ENGINES, COLORS, strict=True)),
            "measured_reference": "White curve in each panel; no separate measured animation",
            "render_script_sha256": sha(Path(__file__)),
            "asset_manifest_sha256": sha(Path(assets) / "manifest.json"),
            "render_only_interpolation": "linear, 100 Hz saved samples -> 30 fps",
            "source": str(source),
        }
        file.with_suffix(".json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--font", type=Path)
    p.add_argument("--concat", action="store_true")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--assets", type=Path, required=True, help="CAD export directory with manifest.json")
    p.add_argument("--grams", type=int, nargs="+", default=[200, 100, 500])
    p.add_argument("--trajectory", nargs="+", default=list(TITLES))
    p.add_argument("--preview", type=float)
    a = p.parse_args()
    global FONTS
    FONTS = load_fonts(a.font)
    dataset = Dataset(a.dataset)
    a.output.mkdir(parents=True, exist_ok=True)
    rows = dataset.rows
    for grams in a.grams:
        for trajectory in a.trajectory:
            row = next(
                r
                for r in rows
                if r["mass_g"] == grams
                and r["trajectory"] == trajectory
                and r["kp"] == 20
                and r["split"] in ("final_test", "long_test")
            )
            render(a.source.resolve(), a.output.resolve(), a.assets, row, dataset, a.preview)

    if a.concat and a.preview is None:
        concatenate(a.output.resolve(), a.grams, a.trajectory)


def concatenate(videos, loads, trajectories):
    for grams in loads:
        paths = [videos / f"rs05_{grams}g_{key}_complete.mp4" for key in trajectories]
        listing = videos / f"concat_{grams}g.txt"
        listing.write_text("".join(f"file '{p.name}'\n" for p in paths))
        output = videos / f"rs05_{grams}g_all_profiles_complete.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-n",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
        )
        position = 0
        segments = []
        for path in paths:
            metadata = json.loads(path.with_suffix(".json").read_text())
            segments.append(
                {
                    "file": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "record": metadata["record"],
                    "start_frame": position,
                    "frames": metadata["frames"],
                    "duration_s": metadata["duration_s"],
                }
            )
            position += metadata["frames"]
        output.with_suffix(".json").write_text(
            json.dumps(
                {
                    "video": output.name,
                    "frames": position,
                    "fps": 30,
                    "duration_s": position / 30,
                    "segments": segments,
                    "editing": "Every source video included in full, no trims or speed changes",
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()

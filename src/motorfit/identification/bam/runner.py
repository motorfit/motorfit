"""Thin, snapshot-driven entry points into unmodified upstream BAM tools."""

import argparse
import json
import math
import runpy
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from motorfit.devices.spec import MotorSpec

from .actuator import register


def _read_spec(path: Path, identity_key: str) -> MotorSpec:
    data = json.loads(path.read_text())
    spec = MotorSpec.from_dict(data["motor_spec"])
    if data[identity_key] != spec.name:
        raise ValueError(f"{path}: {identity_key} does not match motor_spec.name")
    return spec


def _log_spec(directory: Path) -> MotorSpec:
    files = sorted(directory.glob("*.json"))
    if not files:
        raise ValueError(f"No processed JSON logs under {directory}")
    spec = _read_spec(files[0], "motor")
    for path in files[1:]:
        other = _read_spec(path, "motor")
        if other != spec:
            raise ValueError(f"Mixed motor snapshots in {directory}: {spec.name} / {other.name}")
    return spec


def load_model(path: Path):
    """Load fitted parameters using their complete, saved motor definition."""
    from bam.model import load_model as upstream_load_model

    path = Path(path)
    register(_read_spec(path, "actuator"))
    return upstream_load_model(str(path))


def bam_tool(name: str, arguments: list[str]) -> None:
    spec = None
    arguments = list(arguments)
    if name == "jitter" and not {"--help", "-h"}.intersection(arguments):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--logdir", type=Path, required=True)
        options, remaining = parser.parse_known_args(arguments)
        with _raw_directory(options.logdir) as raw:
            _jitter(["--logdir", raw, *remaining])
        return
    if name in {"fit", "plot"} and not {"--help", "-h"}.intersection(arguments):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--logdir", type=Path, required=True)
        parser.add_argument("--actuator")
        if name == "fit":
            parser.add_argument("--output", type=Path, default=Path("params.json"))
            parser.add_argument("--reset_period", type=float)
            parser.add_argument("--load-study")
            parser.add_argument("--model")
        if name == "plot":
            parser.add_argument("--params", nargs="+", default=["params.json"])
        options, _ = parser.parse_known_args(arguments)
        if name == "fit" and options.load_study is not None:
            raise NotImplementedError(
                "The pinned BAM revision does not implement --load-study; "
                "remove it to start a new study."
            )
        spec = _log_spec(options.logdir)
        if options.actuator is not None and options.actuator != spec.name:
            raise ValueError(f"--actuator {options.actuator} does not match logs for {spec.name}")
        if options.actuator is None:
            arguments.extend(["--actuator", spec.name])
        parameter_paths = []
        if name == "fit" and "--eval" in arguments:
            parameter_paths = [options.output]
        elif name == "plot" and {"--sim", "--sim-mujoco", "--sim-mjlab"}.intersection(arguments):
            parameter_paths = options.params
        for path in parameter_paths:
            if _read_spec(Path(path), "actuator") != spec:
                raise ValueError(f"{path}: parameter motor snapshot differs from the logs")
        register(spec)

        if name == "fit" and "--eval" in arguments:
            from .fitting import evaluate

            model = load_model(options.output)
            if options.model is not None and options.model != model.name:
                raise ValueError(f"--model {options.model} does not match {options.output}")
            print(f"Score: {evaluate(model, options.logdir, options.reset_period):.8g} rad")
            return

    _run(name, arguments, spec)


def _jitter(arguments: list[str]) -> None:
    import matplotlib.pyplot as plt

    original = plt.hist

    def histogram(values, **kwargs):
        # Upstream hardcodes 100 bins, which NumPy cannot represent for nearly
        # constant intervals. Automatic binning changes only the visualization.
        return original(values, **{**kwargs, "bins": "auto"})

    try:
        plt.hist = histogram
        _run("jitter", arguments)
    finally:
        plt.hist = original


def _run(name: str, arguments: list[str], spec: MotorSpec | None = None) -> None:

    old_argv = sys.argv
    try:
        sys.argv = [f"bam.{name}", *arguments]
        if name == "fit" and spec is not None:
            from .fitting import fit

            fit(spec)
        else:
            runpy.run_module(f"bam.{name}", run_name="__main__")
    finally:
        sys.argv = old_argv


@contextmanager
def _raw_directory(raw: Path):
    """Expose nested per-run raw files to upstream tools' flat-directory input."""
    files = [raw] if raw.is_file() else sorted(raw.rglob("raw.json"))
    if not files:
        raise ValueError(f"No raw.json recordings under {raw}")
    with tempfile.TemporaryDirectory(prefix="motorfit-process-") as temporary:
        for index, path in enumerate(files):
            _read_spec(path, "motor")
            data = json.loads(path.read_text())
            if len(data["entries"]) < 2:
                raise ValueError(f"{path}: resampling needs at least two samples")
            shutil.copyfile(path, Path(temporary) / f"{index:04d}_{path.parent.name}.json")
        yield temporary


def process(raw: Path, output: Path, dt: float) -> None:
    """Feed recorded files to BAM's resampler, preserving their metadata."""
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be positive and finite")
    output.mkdir(parents=True, exist_ok=True)
    with _raw_directory(raw) as temporary:
        _run("process", ["--raw", temporary, "--logdir", str(output), "--dt", str(dt)])

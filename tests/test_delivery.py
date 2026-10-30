"""The minimal example must work without the historic tree or a CAN interface."""

import json
import shutil
from pathlib import Path

import can
import pytest

from motor_identification.dataset import Dataset
from motor_identification.offline import run

ROOT = Path(__file__).resolve().parents[1]


def test_relocated_example_and_input_tampering(monkeypatch, tmp_path):
    moved = tmp_path / "another checkout"
    shutil.copytree(ROOT / "examples/offline", moved / "examples/offline")
    monkeypatch.chdir(tmp_path)

    def no_can(*args, **kwargs):
        raise AssertionError("Offline example tried to open CAN")

    monkeypatch.setattr(can, "Bus", no_can)
    manifest = moved / "examples/offline/manifest.json"
    summary = run(manifest, tmp_path / "result")
    assert summary["records"] == 3 and summary["parameters_refitted"] is False
    assert max(r["reference_max_abs_difference"] for r in summary["metrics"]) < 1e-10
    assert (tmp_path / "result/comparison.png").is_file()
    dataset = Dataset(manifest)
    assert dataset.model_path == moved / "examples/offline/model.json"
    altered = dataset.resolve(dataset.rows[0]["processed_path"])
    altered.write_text(altered.read_text() + " ")
    with pytest.raises(ValueError, match="SHA-256"):
        dataset.log(dataset.rows[0])
    # Dataset paths are portable even when historical JSON metadata had absolute paths.
    metadata = json.loads(manifest.read_text())
    metadata["model_path"] = str(dataset.model_path)
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="relative"):
        Dataset(manifest)

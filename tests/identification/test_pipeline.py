"""One real upstream process/fit round trip, entirely offline."""

import json
import math
import time
import tomllib
from pathlib import Path

import can
import optuna
import pytest
from bam.actuators import actuators

from motor_identification.devices.registry import command_value
from motor_identification.devices.robstride.models import MotorSpec
from motor_identification.identification.bam import bam_tool, load_model, process


@pytest.mark.parametrize("profile", ["robstride/rs06", "damiao/4310"])
def test_upstream_pipeline_and_snapshot_load(monkeypatch, tmp_path, capsys, profile):
    def no_hardware(*args, **kwargs):
        raise AssertionError("This pipeline test must not open CAN")

    monkeypatch.setattr(can, "Bus", no_hardware)
    model_path = Path(__file__).parents[2] / f"configs/motors/{profile}.toml"
    spec = MotorSpec.from_dict(tomllib.loads(model_path.read_text()))
    monkeypatch.chdir(tmp_path)

    raw = tmp_path / "raw/run/raw.json"
    raw.parent.mkdir(parents=True)
    data = {
        "motor": spec.name,
        "motor_spec": spec.to_dict(),
        "mass": 0.1248,
        "arm_mass": 0.11,
        "length": 0.2,
        "kp": 30.0,
        "kd": 2.0,
        "kp_encoded": command_value(spec, "kp", 30.0),
        "kd_encoded": command_value(spec, "kd", 2.0),
        "vin": 23.0,
        "synthetic": True,
        "entries": [],
    }
    for i in range(31):
        t = i * 0.01
        data["entries"].append(
            {
                "timestamp": t,
                "position": 0.02 * math.sin(t),
                "speed": 0.02 * math.cos(t),
                "load": 0.0,
                "goal_position": 0.03 * math.sin(t),
                "input_volts": 23.0,
                "torque_enable": True,
            }
        )
    raw.write_text(json.dumps(data))
    second = tmp_path / "raw/second/raw.json"
    second.parent.mkdir()
    second.write_text(
        json.dumps({**data, "kp": 15.0, "kp_encoded": command_value(spec, "kp", 15.0)})
    )
    third = tmp_path / "raw/third/raw.json"
    third.parent.mkdir()
    third.write_text(
        json.dumps({**data, "kp": 20.0, "kp_encoded": command_value(spec, "kp", 20.0)})
    )
    processed = tmp_path / "processed"
    process(tmp_path / "raw", processed, 0.005)
    result = json.loads(next(processed.glob("*.json")).read_text())
    assert result["dt"] == 0.005 and len(result["entries"]) == 60
    assert result["synthetic"] is True
    assert result["motor_spec"] == spec.to_dict()

    params = tmp_path / "selected-model.json"
    bam_tool(
        "fit",
        [
            "--logdir",
            str(processed),
            "--model",
            "m1",
            "--trials",
            "2",
            "--validation_kp",
            "30",
            "--reset_period",
            "0.05",
            "--output",
            str(params),
        ],
    )
    fitted = json.loads(params.read_text())
    assert fitted["model"] == "m1" and fitted["actuator"] == spec.name
    assert fitted["motor_spec"] == spec.to_dict()
    assert math.isfinite(fitted["identification"]["training_mae_rad"])
    assert math.isfinite(fitted["identification"]["validation_mae_rad"])
    assert all(math.isfinite(value) for value in fitted.values() if isinstance(value, float))
    del actuators[spec.name]
    loaded = load_model(params)
    assert loaded.actuator.get_extra_inertia() == fitted["armature"]
    assert loaded.actuator.spec == spec

    assert not (tmp_path / "params.json").exists()
    bam_tool("fit", ["--logdir", str(processed), "--eval", "--output", str(params)])
    assert "Score:" in capsys.readouterr().out

    import matplotlib.pyplot as plt

    monkeypatch.setattr(plt, "show", lambda: None)
    bam_tool("jitter", ["--logdir", str(tmp_path / "raw")])
    assert "Loaded 3 logs, 90 intervals" in capsys.readouterr().out
    plt.close("all")
    with pytest.raises(NotImplementedError, match="does not implement --load-study"):
        bam_tool("fit", ["--logdir", str(processed), "--load-study", "missing.db"])

    # Explicitly reject mixed snapshots instead of silently selecting one motor.
    other = {**result, "motor": "another-model"}
    other["motor_spec"] = {**spec.to_dict(), "name": "another-model"}
    (processed / "other.json").write_text(json.dumps(other))
    with pytest.raises(ValueError, match="Mixed motor snapshots"):
        bam_tool("fit", ["--logdir", str(processed), "--model", "m1"])


def test_periodic_snapshot_and_interrupted_fit(monkeypatch, tmp_path):
    """An output inspected during fitting and after Ctrl+C must remain loadable."""
    spec = MotorSpec.from_dict(
        tomllib.loads(
            (Path(__file__).parents[2] / "configs/motors/robstride/rs05.toml").read_text()
        )
    )
    logdir = tmp_path / "logs"
    logdir.mkdir()
    (logdir / "example.json").write_text(
        json.dumps(
            {
                "motor": spec.name,
                "motor_spec": spec.to_dict(),
                "mass": 0.1,
                "arm_mass": 0.01,
                "length": 0.2,
                "kp": 5.0,
                "kd": 0.1,
                "dt": 0.005,
                "entries": [
                    {"position": 0.1, "speed": 0.0, "goal_position": 0.0, "torque_enable": True}
                    for _ in range(10)
                ],
            }
        )
    )
    params = tmp_path / "result.json"
    original = optuna.study.Study.optimize

    def interrupt_after_completed_trial(study, objective, *args, **kwargs):
        objective.__globals__["last_log"] = time.time() - 1

        def inspect_and_interrupt(study, trial):
            assert load_model(params).actuator.spec == spec
            raise KeyboardInterrupt

        kwargs["callbacks"].append(inspect_and_interrupt)
        return original(study, objective, *args, **kwargs)

    monkeypatch.setattr(optuna.study.Study, "optimize", interrupt_after_completed_trial)
    with pytest.raises(KeyboardInterrupt):
        bam_tool(
            "fit",
            ["--logdir", str(logdir), "--model", "m1", "--trials", "3", "--output", str(params)],
        )
    assert optuna.study.Study.optimize is interrupt_after_completed_trial
    assert load_model(params).actuator.spec == spec
    assert math.isfinite(json.loads(params.read_text())["identification"]["training_mae_rad"])

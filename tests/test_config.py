"""Configuration composition and separation of model data from physical zero."""

import shutil
from pathlib import Path

from motorfit.config import load_setup, save_zero


def test_setup_paths_and_per_device_coordinates(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[1]
    configs = tmp_path / "configs"
    shutil.copytree(root / "configs", configs, ignore=shutil.ignore_patterns("local"))
    setup = configs / "setups/rs05_pendulum.toml"
    original = setup.read_text()
    profile = configs / "motors/robstride/rs05.toml"
    model_text = profile.read_text()
    monkeypatch.chdir(tmp_path.parent)

    config = load_setup(setup)
    assert config["motor"]["name"] == "rs05"
    assert config["fixture"]["mass"] == 0.1248
    assert config["fixture"]["vin"] == 23.0
    assert config["recording"]["kp"] == 30.0
    assert config["recording"]["trajectory"] == "sin_time_square"
    assert config["recording"]["duration_s"] == 6.0
    assert "zero_rad" not in config["coordinate"]
    local = Path(config["coordinate_file"])
    assert local == configs / "local/rs05_example_can0.toml"
    save_zero(local, 2.25, config["coordinate"]["convention"])
    save_zero(local, 2.5, config["coordinate"]["convention"])
    assert load_setup(setup)["coordinate"]["zero_rad"] == 2.5

    # Same model on a second mounted device must not inherit the first zero.
    other = setup.with_name("rs05_second.toml")
    other.write_text(original.replace("rs05_example_can0.toml", "rs05_second.toml"))
    assert "zero_rad" not in load_setup(other)["coordinate"]
    assert setup.read_text() == original and profile.read_text() == model_text

    # Selecting another model changes only the reference, not Python code.
    for name in ("rs01", "rs02", "rs06"):
        other.write_text(original.replace("rs05.toml", f"{name}.toml"))
        assert load_setup(other)["motor"]["name"] == name

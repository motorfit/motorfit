"""Compose one setup from motor, fixture, acquisition, and local coordinates."""

import json
import math
import tomllib
from pathlib import Path


def load_fixture(path: Path) -> dict:
    """Load fixture geometry and check a supplied point-load mass breakdown."""
    fixture = tomllib.loads(Path(path).read_text())
    components = ("weight_mass", "bolt_mass", "nut_mass")
    if any(key in fixture for key in components):
        if not all(key in fixture for key in components):
            raise ValueError("Fixture mass breakdown requires weight_mass, bolt_mass and nut_mass")
        masses = [fixture[key] for key in components]
        if not all(math.isfinite(value) and value >= 0 for value in masses):
            raise ValueError("Fixture component masses must be finite and non-negative")
        if not math.isclose(fixture["mass"], math.fsum(masses), rel_tol=0, abs_tol=1e-12):
            raise ValueError("Fixture mass must equal weight_mass + bolt_mass + nut_mass")
    return fixture


def load_setup(path: Path) -> dict:
    path = Path(path).resolve()
    setup = tomllib.loads(path.read_text())

    def component(key):
        return tomllib.loads((path.parent / setup[key]).read_text())

    coordinate_path = (path.parent / setup["coordinate_file"]).resolve()
    coordinate = dict(setup["coordinate"])
    if coordinate_path.exists():
        coordinate.update(tomllib.loads(coordinate_path.read_text())["coordinate"])
    return {
        "motor": component("motor"),
        "fixture": {
            **load_fixture(path.parent / setup["fixture"]),
            "vin": setup["supply"]["voltage"],
        },
        "recording": component("acquisition"),
        "device": setup["device"],
        "coordinate": coordinate,
        "coordinate_file": str(coordinate_path),
        "setup_file": str(path),
    }


def save_zero(path: Path, zero_rad: float, convention: str) -> None:
    """Write the mounted device's software coordinate, outside shared profiles."""
    if not math.isfinite(zero_rad):
        raise ValueError("zero_rad must be finite")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"[coordinate]\nconvention = {json.dumps(convention)}\nzero_rad = {zero_rad!r}\n"
    )

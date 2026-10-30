"""Keep the operator's load/bolt mapping consistent through setup and dynamics."""

import math
from pathlib import Path

import pytest

from motor_identification.config import load_fixture
from motor_identification.rigs.pendulum import Pendulum

FIXTURES = Path(__file__).resolve().parents[1] / "configs/fixtures"


@pytest.mark.parametrize(
    "weight_g,bolt_g,total_kg,inertia,gravity_peak",
    [
        (100, 20.5, 0.1248, 0.006401478576300897, 0.34194633792699125),
        (200, 25.1, 0.2294, 0.010585478576300896, 0.5471014559269913),
        (500, 25.1, 0.5294, 0.022585478576300902, 1.1355004559269912),
        (1000, 25.1, 1.0294, 0.0425854785763009, 2.116165455926991),
    ],
)
def test_confirmed_fixture_masses_and_dynamics(weight_g, bolt_g, total_kg, inertia, gravity_peak):
    fixture = load_fixture(FIXTURES / f"pendulum_{weight_g}g_200mm.toml")
    assert fixture["weight_mass"] == pytest.approx(weight_g / 1000)
    assert fixture["bolt_mass"] == pytest.approx(bolt_g / 1000)
    assert fixture["nut_mass"] == 0.0043
    assert fixture["mass"] == total_kg
    pendulum = Pendulum(fixture)
    assert pendulum.compute_mass(0, 0) == pytest.approx(inertia)
    assert pendulum.compute_bias(math.pi / 2, 0) == pytest.approx(-gravity_peak)


def test_stale_total_cannot_override_corrected_components(tmp_path):
    path = tmp_path / "wrong-500g.toml"
    text = (FIXTURES / "pendulum_500g_200mm.toml").read_text()
    path.write_text(text.replace("mass = 0.5294", "mass = 0.5248", 1))
    with pytest.raises(ValueError, match="mass must equal"):
        load_fixture(path)


def test_legacy_fixture_without_component_breakdown_remains_readable():
    assert load_fixture(FIXTURES / "unloaded_shaft.toml")["mass"] == 0.0


def test_partial_breakdown_is_rejected(tmp_path):
    path = tmp_path / "partial.toml"
    path.write_text("mass = 0.5294\nweight_mass = 0.5\n")
    with pytest.raises(ValueError, match="requires weight_mass"):
        load_fixture(path)

"""Regression to sealed release predictions and an independent torque impulse."""

import json
from pathlib import Path

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from motor_identification.dataset import Dataset  # noqa: E402
from motor_identification.identification.mujoco import M1Parameters  # noqa: E402
from motor_identification.validation.release import CASES, build_library, replay  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    return build_library(tmp_path_factory.mktemp("release-library"))


def test_frozen_release_regression(native):
    dataset = Dataset(ROOT / "examples/offline/manifest.json")
    row = next(r for r in dataset.rows if r["mass_g"] == 200)
    events = json.loads((ROOT / "tests/fixtures/release/events.json").read_text())[row["id"]]
    params = M1Parameters.load(dataset.model_path)
    for case in CASES:
        prediction, diagnostic = replay(
            dataset.log(row),
            params,
            ROOT / "tests/fixtures/release/scene.xml",
            0.0000625,
            events[case],
            native,
        )
        with np.load(ROOT / f"tests/fixtures/release/{case}.npz") as reference:
            np.testing.assert_allclose(prediction, reference["prediction"], rtol=0, atol=1e-12)
        assert abs(diagnostic[0] - events[case]) < 1e-10
        assert diagnostic[7] == 0


def test_event_splits_a_controller_step_with_correct_impulse(native):
    dt, event = 0.002, 0.00312345
    model = mujoco.MjModel.from_xml_string(f'''<mujoco>
      <option timestep="{dt}" gravity="0 0 0" integrator="implicitfast"/>
      <worldbody><body><joint name="j" type="hinge"/>
      <inertial mass="1" pos="0 0 0" diaginertia="1 1 1"/></body></worldbody>
      <actuator><motor joint="j"/></actuator></mujoco>''')
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    p = np.array([0.0, 0.0, 0.0, 1.0, 1.0, -5.5, 5.5])
    output, diagnostic = np.empty((5, 5)), np.zeros(8)
    assert (
        native.rs05_release_event(
            model._address,
            data._address,
            5,
            5,
            event,
            p,
            np.zeros(25),
            np.ones(5),
            output,
            diagnostic,
        )
        == 0
    )
    assert abs(data.qvel[0] - event) < 1e-12
    assert abs(diagnostic[5] - event) < 1e-12
    assert diagnostic[6] == 1 and model.opt.timestep == dt

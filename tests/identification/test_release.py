"""Check release-event integration against an analytical torque impulse."""

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from motorfit.validation.release import build_library  # noqa: E402


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    return build_library(tmp_path_factory.mktemp("release-library"))


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

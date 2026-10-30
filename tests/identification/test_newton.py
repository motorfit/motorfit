from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("newton")
pytest.importorskip("mujoco_warp")


from motorfit.identification.newton import NewtonPendulumBatch
from motorfit.rigs.pendulum import Pendulum


def test_imported_inertia_gravity_and_ref_coordinates(m1_params, pendulum_log):
    params = replace(m1_params, friction_base=0, friction_viscous=0, command_delay=0)
    logs = [dict(pendulum_log, mass=mass) for mass in (0.1248, 0.2294, 0.5294)]
    batch = NewtonPendulumBatch(logs, params)
    q0 = batch.position()
    nominal, torque, _ = batch.step(q0, np.ones(3))
    np.testing.assert_allclose(nominal, 0, atol=1e-12)
    for i, log in enumerate(logs):
        rig = Pendulum(log)
        expected = (
            (rig.compute_bias(q0[i] + params.q_offset, 0) + torque[i])
            / (rig.compute_mass(0, 0) + params.armature)
            * batch.dt
        )
        assert batch.velocity()[i] == pytest.approx(expected, rel=5e-6, abs=1e-8)
    np.testing.assert_allclose(batch.mj_model.dof_armature, params.armature, rtol=1e-6)
    np.testing.assert_allclose(batch.mj_model.opt.gravity, [0, 0, -9.80665], rtol=1e-6)


def test_newton_delay_clamp_disable_friction_and_replay_reset(m1_params, pendulum_log):
    batch = NewtonPendulumBatch([pendulum_log, deepcopy(pendulum_log)], m1_params)
    q0 = batch.position().copy()
    target = None
    for _ in range(4):
        nominal, torque, target = batch.step(np.array([100, -100]), np.array([True, False]))
    assert target[0] > q0[0]
    assert nominal[0] == m1_params.torque_max
    assert torque[0] == pytest.approx(m1_params.torque_ratio * m1_params.torque_max, rel=1e-6)
    assert torque[1] == 0
    assert batch.position()[0] != batch.position()[1]
    np.testing.assert_allclose(batch.mj_model.dof_frictionloss, m1_params.friction_base)
    np.testing.assert_allclose(batch.mj_model.dof_damping, m1_params.friction_viscous)
    for first, second in zip(batch.rollout(), batch.rollout(), strict=True):
        np.testing.assert_array_equal(first, second)

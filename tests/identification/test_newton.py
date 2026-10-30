from copy import deepcopy
from dataclasses import replace
from functools import partial

import numpy as np
import pytest

pytest.importorskip("newton")
pytest.importorskip("mujoco_warp")

import mujoco

from motor_identification.identification.newton import NewtonPendulumBatch
from motor_identification.rigs.pendulum import Pendulum
from motor_identification.rigs.rs05_bench import bench_properties, bench_xml


def test_implicitfast_uses_implicit_viscous_update(m1_params, pendulum_log):
    params = replace(m1_params, friction_base=0, friction_viscous=0.5, command_delay=0)
    log = deepcopy(pendulum_log)
    log.update(kp=0, kd=0)
    log["entries"] = [
        dict(position=-params.q_offset, speed=2.0, goal_position=0, torque_enable=False)
    ] * 2
    batch = NewtonPendulumBatch([log], params, integrator="implicitfast")
    assert batch.mj_model.opt.integrator == mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    batch.step(np.zeros(1), np.zeros(1))
    inertia = Pendulum(log).compute_mass(0, 0) + params.armature
    expected = 2.0 / (1 + batch.dt * params.friction_viscous / inertia)
    assert batch.velocity()[0] == pytest.approx(expected, rel=1e-6)


def test_complete_cad_import_and_component_inertia(m1_params, bench_assets, bench_logs):
    params = replace(m1_params, friction_base=0, friction_viscous=0, command_delay=0)
    batch = NewtonPendulumBatch(
        bench_logs, params, xml_factory=partial(bench_xml, assets=bench_assets)
    )
    assert batch.model.shape_count >= 30
    q0 = batch.position()
    _, torque, _ = batch.step(q0, np.ones(3))
    for i, log in enumerate(bench_logs):
        mass, com, inertia = bench_properties(log, bench_assets)
        angle = q0[i] + params.q_offset
        gravity = -9.80665 * mass * (com[0] * np.cos(angle) - com[2] * np.sin(angle))
        pivot_inertia = inertia[1, 1] + mass * (com[0] ** 2 + com[2] ** 2) + params.armature
        expected = (gravity + torque[i]) / pivot_inertia * batch.dt
        assert batch.velocity()[i] == pytest.approx(expected, rel=1e-5, abs=1e-8)


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


def test_newton_stiction_breakaway_and_viscous_force(m1_params, pendulum_log):
    logs = []
    for factor in (0.8, 1.2):
        log = deepcopy(pendulum_log)
        log.update(
            kp=0, kd=0, feedforward_torque=factor * m1_params.friction_base / m1_params.torque_ratio
        )
        log["entries"] = [
            dict(position=-m1_params.q_offset, speed=0, goal_position=0, torque_enable=True)
        ] * 20
        logs.append(log)
    batch = NewtonPendulumBatch(logs, m1_params, dt=0.001)
    q0 = batch.position()
    for _ in range(100):
        batch.step(np.zeros(2), np.ones(2))
    change = batch.position() - q0
    assert abs(change[0]) < 1e-5
    assert change[1] > 1e-3
    batch.state.joint_qd.assign(np.array([2.0, 2.0], dtype=np.float32))
    batch.step(np.zeros(2), np.zeros(2))
    np.testing.assert_allclose(
        batch.mj_data.qfrc_passive, -2 * m1_params.friction_viscous, rtol=1e-6
    )
    np.testing.assert_allclose(batch.mj_data.qfrc_constraint, -m1_params.friction_base, rtol=1e-6)

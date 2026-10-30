from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("mjlab")
pytest.importorskip("torch")

import torch

from motorfit.identification.mjlab import MjlabPendulumBatch
from motorfit.rigs.pendulum import Pendulum


def test_gpu_inertia_gravity_and_offset(m1_params, pendulum_log):
    params = replace(m1_params, friction_base=0, friction_viscous=0, command_delay=0)
    log = dict(pendulum_log, mass=0.2294)
    batch = MjlabPendulumBatch([log], params)
    q0 = batch.sim.data.qpos[...].clone()
    _, torque, _ = batch.step(q0, torch.ones_like(q0))
    rig = Pendulum(log)
    expected = (
        (rig.compute_bias(q0.item() + params.q_offset, 0) + torque.item())
        / (rig.compute_mass(0, 0) + params.armature)
        * batch.dt
    )
    assert batch.sim.data.qvel[...].item() == pytest.approx(expected, rel=5e-6, abs=1e-8)
    assert batch.sim.mj_model.dof_armature[0] == params.armature


def test_gpu_stiction_breakaway_viscosity_and_partial_reset(m1_params, pendulum_log):
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
    batch = MjlabPendulumBatch(logs, m1_params, dt=0.001)
    q0 = batch.sim.data.qpos[...].clone()
    goals = torch.zeros_like(q0)
    for _ in range(100):
        batch.step(goals, torch.ones_like(goals))
    change = (batch.sim.data.qpos[...] - q0).cpu().numpy().ravel()
    assert abs(change[0]) < 1e-5
    assert change[1] > 1e-3
    batch.sim.data.qvel[:] = 2.0
    _, torque, _ = batch.step(goals, torch.zeros_like(goals))
    assert torch.all(torque == 0)
    np.testing.assert_allclose(
        batch.sim.data.qfrc_passive[...].cpu(), -2 * m1_params.friction_viscous, rtol=1e-5
    )
    np.testing.assert_allclose(
        batch.sim.data.qfrc_constraint[...].cpu(), -m1_params.friction_base, rtol=1e-5
    )
    q1, v1 = batch.sim.data.qpos[1].clone(), batch.sim.data.qvel[1].clone()
    history1 = batch.delay.buffer[:, 1].clone()
    batch.reset(torch.tensor([0], device="cuda:0"))
    assert torch.equal(batch.sim.data.qpos[1], q1)
    assert torch.equal(batch.sim.data.qvel[1], v1)
    assert torch.equal(batch.delay.buffer[:, 1], history1)
    assert torch.equal(batch.sim.data.qpos[0], batch.initial_q[0])
    batch.kp.fill_(30)
    batch.feedforward.zero_()
    for _ in range(8):
        nominal, torque, _ = batch.step(torch.full_like(goals, 100), batch.tensor([[1], [0]]))
    assert nominal[0].item() == m1_params.torque_max
    assert torque[0].item() == pytest.approx(
        m1_params.torque_max * m1_params.torque_ratio, rel=1e-6
    )
    assert torque[1].item() == 0

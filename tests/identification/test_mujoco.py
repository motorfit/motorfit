import numpy as np
import pytest

pytest.importorskip("mujoco")

import mujoco
from bam.simulate import fractional_delay_shift

from motorfit.identification.mujoco import (
    FractionalDelay,
    M1Parameters,
    PendulumReplay,
)
from motorfit.rigs.pendulum import Pendulum


@pytest.fixture
def params():
    return M1Parameters(
        1.1639233433530467,
        0.00023631471353394536,
        -0.001214251462938909,
        0.006293081495280065,
        0.04300222579284436,
        0.002987922558477437,
        -5.5,
        5.5,
    )


@pytest.fixture
def log():
    return dict(
        mass=0.1248,
        arm_mass=0.11,
        length=0.2,
        arm_com=0.0900802043205295,
        arm_inertia=0.0014073185763008957,
        hub_inertia=0.00000216,
        kp=30,
        kd=0.8,
        dt=0.01,
        entries=[dict(position=0.1, speed=0, goal_position=0.1, torque_enable=True)] * 20,
    )


def test_causal_delay_equals_bam_and_resets_selected_env():
    delay = 0.035
    goals = np.random.default_rng(4).normal(size=(100, 3, 2))
    ring = FractionalDelay(delay, 0.01, goals[0])
    got = np.array([ring.push(g) for g in goals])
    np.testing.assert_allclose(got, fractional_delay_shift(goals, delay, 0.01), atol=1e-15)
    other = ring.buffer[:, [0, 2]].copy()
    ring.reset(np.full((1, 2), 17), [1])
    np.testing.assert_equal(ring.buffer[:, [0, 2]], other)
    np.testing.assert_equal(ring.buffer[:, 1], 17)


def test_mass_gravity_and_offset_match_measured_fixture(log, params):
    log["mass"] = 0.2294
    replay = PendulumReplay(log, params)
    rig = Pendulum(log)
    for q in np.linspace(-1, 1, 9):
        replay.data.qpos[0] = q
        mujoco.mj_forward(replay.model, replay.data)
        inertia = np.empty(replay.model.nv)
        mujoco.mj_mulM(replay.model, replay.data, inertia, np.ones(replay.model.nv))
        assert inertia[0] == pytest.approx(rig.compute_mass(q, 0) + params.armature)
        assert -replay.data.qfrc_bias[0] == pytest.approx(
            rig.compute_bias(q + params.q_offset, 0), abs=1e-14
        )


def test_sticking_breakaway_and_viscous_dissipation(log, params):
    replay = PendulumReplay(log, params, dt=0.001)
    replay.model.opt.gravity[:] = 0
    replay.kp = replay.kd = 0
    for factor in (0.8, 1.2):
        replay.reset()
        replay.log["feedforward_torque"] = factor * params.friction_base / params.torque_ratio
        q0 = replay.data.qpos[0]
        for _ in range(500):
            replay.step(0.1, True)
        delta = replay.data.qpos[0] - q0
        assert delta < 1e-5 if factor < 1 else delta > 0.05
    replay.log["feedforward_torque"] = 0
    replay.data.qvel[0] = 2.0
    replay.step(0.1, False)
    assert replay.data.qfrc_passive[0] == pytest.approx(-2 * params.friction_viscous)
    assert replay.data.qfrc_constraint[0] == pytest.approx(-params.friction_base)
    assert 0 < replay.data.qvel[0] < 2


def test_damiao_snapshot_replay_preserves_encoded_controller(tmp_path, log):
    import json
    import tomllib
    from pathlib import Path

    from motorfit.devices.registry import command_value
    from motorfit.devices.spec import MotorSpec

    root = Path(__file__).resolve().parents[2]
    spec = MotorSpec.from_dict(
        tomllib.loads((root / "configs/motors/damiao/4310.toml").read_text())
    )
    # Synthetic parameters; no claim of identified hardware properties.
    snapshot = dict(
        model="m1",
        actuator=spec.name,
        motor_spec=spec.to_dict(),
        torque_ratio=1.1,
        armature=0.0001,
        q_offset=0,
        command_delay=0.002,
        friction_base=0.01,
        friction_viscous=0.001,
    )
    path = tmp_path / "dm4310.json"
    path.write_text(json.dumps(snapshot))
    parameters = M1Parameters.load(path)
    log.update(
        kp_encoded=command_value(spec, "kp", 20),
        kd_encoded=command_value(spec, "kd", 0.8),
        goal_speed=command_value(spec, "velocity", 0),
        feedforward_torque=command_value(spec, "torque", 0),
    )
    replay = PendulumReplay(log, parameters)
    assert replay.kp == pytest.approx(163 * 500 / 4095)
    assert parameters.torque_min == -10 and parameters.torque_max == 10
    nominal, torque, _ = replay.step(100, True)
    assert nominal == 10 and torque == pytest.approx(11)
    assert replay.step(-100, False)[1] == 0
    trajectory = replay.rollout()
    assert np.isfinite(trajectory).all()
    np.testing.assert_array_equal(trajectory, replay.rollout())
    snapshot["motor_spec"]["family"] = "hightorque"
    path.write_text(json.dumps(snapshot))
    with pytest.raises(ValueError, match="torque-MIT"):
        M1Parameters.load(path)

import json
import tomllib
from pathlib import Path

import numpy as np
import pytest
from bam.logs import Logs
from bam.model import load_model_from_dict
from bam.simulate import Simulator
from bam.testbench import Pendulum as UpstreamPendulum

from motorfit.devices.robstride.models import MotorSpec
from motorfit.identification.bam.actuator import register
from motorfit.rigs.pendulum import Pendulum


def motor_spec(name):
    path = Path(__file__).parents[2] / f"configs/motors/robstride/{name}.toml"
    return MotorSpec.from_dict(tomllib.loads(path.read_text()))


def make_log(spec, **metadata):
    return {
        "motor": spec.name,
        "motor_spec": spec.to_dict(),
        "mass": 0.1248,
        "arm_mass": 0.11,
        "length": 0.2,
        "arm_com": 0.0900802043205295,
        "arm_inertia": 0.0014073185763008957,
        "hub_inertia": 0.00000216,
        "kp": 30.0,
        "kd": 2.0,
        "dt": 0.001,
        "entries": [
            {
                "timestamp": k * 0.001,
                "position": 0.0,
                "speed": 0.0,
                "goal_position": 0.1,
                "torque_enable": True,
            }
            for k in range(30)
        ],
        **metadata,
    }


@pytest.mark.parametrize("name", ["rs01", "rs02", "rs05", "rs06"])
def test_mit_control_scaling_and_disabled_torque(name):
    spec = motor_spec(name)
    register(spec)
    model = load_model_from_dict({"model": "m1", "actuator": name})
    model.torque_ratio.value = 1.5
    actuator = model.actuator
    actuator.load_log(make_log(spec))

    control = actuator.compute_control(
        np.array([0.1, 0.0, 10.0, -10.0]),
        np.zeros(4),
        np.array([0.5, 0.5, 0.0, 0.0]),
        0.001,
    )
    np.testing.assert_allclose(control, [2.0, -1.0, spec.torque[1], spec.torque[0]])
    np.testing.assert_allclose(
        actuator.compute_torque(control, np.array([True, True, True, False]), 0, 0),
        [3.0, -1.5, spec.torque[1] * 1.5, 0.0],
    )
    assert actuator.compute_torque(None, False, 0, 0) == 0
    assert actuator.get_extra_inertia() == model.armature.value
    assert {"torque_ratio", "armature", "q_offset", "command_delay"} <= set(model.get_parameters())
    assert not {"kt", "R"} & set(model.get_parameters())
    actuator.load_log(make_log(spec, goal_speed=0.0122, feedforward_torque=0.00134))
    assert actuator.compute_control(0.1, 0.0, 0.5, 0.001) == pytest.approx(
        3.0 + 2.0 * (0.0122 - 0.5) + 0.00134
    )
    # Nominal gains identify the experiment; encoded gains drive the simulation.
    actuator.load_log(make_log(spec, kp_encoded=25.0, kd_encoded=1.5))
    assert actuator.compute_control(0.1, 0.0, 0.5, 0.001) == pytest.approx(1.75)


def test_fixture_batch_and_upstream_rollout(tmp_path):
    spec = motor_spec("rs05")
    log_a = make_log(spec)
    log_b = make_log(spec, mass=0.2, length=0.25, kp=20.0, kd=1.0, arm_com=0.1)
    for name, log in [("a", log_a), ("b", log_b)]:
        (tmp_path / f"{name}.json").write_text(json.dumps(log))
    logs = Logs(str(tmp_path))
    batch = logs.make_batch()
    fixture = Pendulum(batch)
    np.testing.assert_allclose(
        fixture.compute_mass(0, 0),
        batch["mass"] * batch["length"] ** 2 + batch["arm_inertia"] + batch["hub_inertia"],
    )
    np.testing.assert_allclose(
        fixture.compute_bias(np.pi / 2, 0),
        -9.80665 * (batch["mass"] * batch["length"] + batch["arm_mass"] * batch["arm_com"]),
    )

    register(spec)
    model = load_model_from_dict({"model": "m1", "actuator": spec.name, "command_delay": 0.0015})
    positions, velocities, controls = Simulator(model).rollout_log(batch, simulate_control=True)
    assert np.asarray(positions).shape == (30, 2)
    assert np.isfinite([positions, velocities, controls]).all()
    assert np.all(np.asarray(positions)[-1] > 0)
    np.testing.assert_allclose(controls[0], batch["kp"] * 0.1)
    for index, log in enumerate(logs.logs):
        scalar = Simulator(model).rollout_log(log, simulate_control=True)
        np.testing.assert_allclose(np.asarray(positions)[:, index], scalar[0])

    standard_log = {key: log_a[key] for key in ("mass", "arm_mass", "length")}
    standard = UpstreamPendulum(standard_log)
    fallback = Pendulum(standard_log)
    assert fallback.compute_mass(0, 0) == pytest.approx(standard.compute_mass(0, 0))
    assert fallback.compute_bias(0.2, 0) == pytest.approx(standard.compute_bias(0.2, 0))

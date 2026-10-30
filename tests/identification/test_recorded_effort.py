import copy

import numpy as np
import pytest
from bam.actuators import actuators
from bam.model import models
from bam.simulate import Simulator

from motorfit.devices.spec import MotorSpec
from motorfit.identification.bam.actuator import register
from motorfit.identification.bam.resample import resample_effort


def model_and_log():
    spec = MotorSpec.from_dict(
        dict(
            name="test_effort",
            family="hightorque",
            position=[-2, 2],
            velocity=[-10, 10],
            torque=[-1, 1],
            kp=[0, 500],
            kd=[0, 5],
        )
    )
    register(spec)
    model = models["m1"]()
    model.set_actuator(actuators[spec.name]())
    log = dict(
        control_source="recorded_effort",
        mass=0.1,
        arm_mass=0.02,
        length=0.2,
        kp=5,
        kd=0.1,
        dt=0.01,
        entries=[
            dict(position=0.0, speed=0.0, goal_position=999, torque_enable=True, control=u)
            for u in (0, 0.1, -0.2, 0.3, 0.0)
        ],
    )
    return model, log


def test_actual_input_not_goal_or_measured_load_drives_bam_and_resets_keep_clock():
    model, log = model_and_log()
    _, _, controls = Simulator(model).rollout_log(log, simulate_control=True, reset_period=0.01)
    assert controls == pytest.approx([0, 0.1, -0.2, 0.3, 0])
    changed = copy.deepcopy(log)
    for e in changed["entries"]:
        e["goal_position"] = -999
        e["load"] = 500
    positions, _, again = Simulator(model).rollout_log(changed, simulate_control=True)
    baseline, _, _ = Simulator(model).rollout_log(log, simulate_control=True)
    np.testing.assert_array_equal(positions, baseline)
    assert again == pytest.approx(controls)
    model.command_delay.value = 0.015
    _, _, delayed = Simulator(model).rollout_log(log, simulate_control=True)
    assert delayed == pytest.approx([0, 0, 0.05, -0.05, 0.05])
    model.actuator.load_log(log)
    state = model.actuator.get_state()
    x = model.actuator.compute_control(0, 0, 0, 0.01)
    model.actuator.set_state(state)
    assert model.actuator.compute_control(0, 0, 0, 0.01) == x


def test_resampling_uses_actual_tx_times_and_step_hold():
    data = dict(completed=True, first_feedback_monotonic=100, entries=[])
    for t, tx, u in [(0, 0.02, 1), (0.1, 0.12, -1), (0.2, 0.22, 0.5)]:
        data["entries"].append(
            dict(
                timestamp=t,
                command_monotonic_time=100 + tx,
                control=u,
                position=t,
                speed=1,
                load=10,
                input_volts=24,
                goal_position=t,
                torque_enable=True,
            )
        )
    out = resample_effort(data, 0.025)
    assert [e["control"] for e in out["entries"]] == [0, 1, 1, 1, 1, -1, -1, -1]
    assert [e["position"] for e in out["entries"]] == pytest.approx(np.arange(0, 0.2, 0.025))
    data["completed"] = False
    with pytest.raises(ValueError, match="incomplete"):
        resample_effort(data, 0.025)

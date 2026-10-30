"""Explicit solver options shared by the CPU and optional backend replays."""

import xml.etree.ElementTree as ET

import mujoco
import numpy as np


def option_values(option):
    values = {}
    for key in dir(option):
        if key.startswith("_"):
            continue
        value = getattr(option, key)
        if isinstance(value, np.ndarray):
            values[key] = value.tolist()
        elif isinstance(value, (int, float)):
            values[key] = value
    return values


def apply_options(expected, option):
    for key, value in expected.items():
        if isinstance(value, list):
            getattr(option, key)[:] = value
        else:
            setattr(option, key, value)
    if option_values(option) != expected:
        raise ValueError("Backend did not retain the requested solver options")


def configure(xml, option_text=None, friction="original", dt=0.002):
    root = ET.fromstring(xml)
    if option_text:
        old = root.find("option")
        index = list(root).index(old)
        root.remove(old)
        option = ET.fromstring(option_text)
        if option.tag != "option":
            raise ValueError("Expected one MJCF option element")
        option.set("timestep", str(dt))
        root.insert(index, option)
    if friction == "default":
        joint = root.find(".//joint")
        joint.attrib.pop("solreffriction", None)
        joint.attrib.pop("solimpfriction", None)
    return ET.tostring(root, encoding="unicode")


def audit_gpu(obj, expected):
    if option_values(obj.sim.mj_model.opt) != expected:
        raise ValueError("mjlab CPU options changed")
    options = obj.sim.wp_model.opt
    checked = []
    for key, value in expected.items():
        if not hasattr(options, key):
            continue
        raw = getattr(options, key)
        raw = raw.numpy() if hasattr(raw, "numpy") else raw
        a = np.asarray(raw)
        np.testing.assert_allclose(
            a, np.broadcast_to(value, a.shape), rtol=1e-6, atol=1e-10, err_msg=key
        )
        checked.append(key)
    if "noslip_iterations" not in checked:
        raise ValueError("This GPU runtime cannot verify the requested NoSlip configuration")
    np.testing.assert_allclose(
        options.impratio_invsqrt.numpy(), expected["impratio"] ** -0.5, rtol=1e-6
    )
    return checked


def gpu_batch(logs, params, factory, dt):
    """Reuse the frozen MIT controller; replace only simulation construction."""
    from mjlab.sim import MujocoCfg, Simulation, SimulationCfg

    from motor_identification.identification.mjlab import (
        MjlabPendulumBatch,
        TorchFractionalDelay,
        fixture_key,
    )

    assert logs and len({fixture_key(log) for log in logs}) == 1
    assert len({log["dt"] for log in logs}) == 1
    model = mujoco.MjModel.from_xml_string(factory(logs[0], params, dt))
    expected = option_values(model.opt)

    class ExactOptions(MujocoCfg):
        def apply(self, target):
            for key, value in expected.items():
                if isinstance(value, list):
                    getattr(target.opt, key)[:] = value
                else:
                    setattr(target.opt, key, value)
            assert option_values(target.opt) == expected

    class ExactSimulationCfg(SimulationCfg):
        def apply_wp_opt(self, wp_opt):
            super().apply_wp_opt(wp_opt)
            # MJWarp put_model raises tolerance to >=1e-6 for float32. Restore
            # the requested 1e-8 in its existing array before graph capture.
            wp_opt.tolerance.fill_(expected["tolerance"])

    # The class's controller/reset/rollout methods remain byte-for-byte unchanged.
    obj = MjlabPendulumBatch.__new__(MjlabPendulumBatch)
    obj.logs, obj.params, obj.dt, obj.device = logs, params, dt, "cuda:0"
    obj.substeps = round(logs[0]["dt"] / obj.dt)
    assert obj.substeps >= 1 and np.isclose(obj.substeps * obj.dt, logs[0]["dt"])
    obj.sim = Simulation(
        num_envs=len(logs),
        model=model,
        device=obj.device,
        cfg=ExactSimulationCfg(njmax=8, nconmax=1, mujoco=ExactOptions()),
    )
    obj.kp = obj.tensor([[log.get("kp_encoded", log["kp"])] for log in logs])
    obj.kd = obj.tensor([[log.get("kd_encoded", log["kd"])] for log in logs])
    obj.goal_speed = obj.tensor([[log.get("goal_speed", 0)] for log in logs])
    obj.feedforward = obj.tensor([[log.get("feedforward_torque", 0)] for log in logs])
    obj.initial_q = obj.tensor([[log["entries"][0]["position"]] for log in logs])
    obj.initial_v = obj.tensor([[log["entries"][0].get("speed", 0)] for log in logs])
    obj.initial_goal = obj.tensor([[log["entries"][0]["goal_position"]] for log in logs])
    obj.delay = TorchFractionalDelay(params.command_delay, obj.dt, obj.initial_goal)
    obj.reset()
    return obj

"""RobStride M1 replay through mjlab Simulation and MuJoCo Warp on the GPU.

The upstream BAM mjlab actuator accepts DC motors only. This adapter implements
the recorded RobStride MIT law instead, with fractional (not integer) delay.
"""

import mujoco
import numpy as np
import torch
from mjlab.sim import MujocoCfg, Simulation, SimulationCfg

from .mujoco import M1Parameters, pendulum_xml


class TorchFractionalDelay:
    """Per-world causal history; no CPU round-trip in the stepping path."""

    def __init__(self, delay: float, dt: float, initial: torch.Tensor):
        steps = delay / dt
        self.whole = int(np.floor(steps))
        self.fraction = steps - self.whole
        self.buffer = initial.unsqueeze(0).expand(self.whole + 2, *initial.shape).clone()
        self.index = 0

    def reset(self, initial, env_ids=slice(None)):
        self.buffer[:, env_ids] = initial

    def push(self, target):
        self.buffer[self.index].copy_(target)
        recent = self.buffer[(self.index - self.whole) % len(self.buffer)]
        older = self.buffer[(self.index - self.whole - 1) % len(self.buffer)]
        result = (1 - self.fraction) * recent + self.fraction * older
        self.index = (self.index + 1) % len(self.buffer)
        return result


class MjlabPendulumBatch:
    """Independent worlds with common fixture geometry and per-log MIT gains."""

    def __init__(
        self,
        logs: list[dict],
        params: M1Parameters,
        dt=0.002,
        device="cuda:0",
        *,
        xml_factory=pendulum_xml,
        integrator="euler",
    ):
        if integrator not in ("euler", "implicitfast"):
            raise ValueError("Expected euler or implicitfast integrator")
        if not logs or any(fixture_key(log) != fixture_key(logs[0]) for log in logs):
            raise ValueError("A batch must share exact fixture geometry")
        if len({log["dt"] for log in logs}) != 1:
            raise ValueError("Recording timesteps must be equal")
        self.logs, self.params, self.dt, self.device = logs, params, dt, device
        self.substeps = round(logs[0]["dt"] / dt)
        if self.substeps < 1 or not np.isclose(self.substeps * dt, logs[0]["dt"]):
            raise ValueError("Physics timestep must divide recording timestep")
        model = mujoco.MjModel.from_xml_string(xml_factory(logs[0], params, dt))
        self.sim = Simulation(
            num_envs=len(logs),
            model=model,
            device=device,
            cfg=SimulationCfg(
                njmax=8,
                nconmax=1,
                mujoco=MujocoCfg(
                    timestep=dt,
                    integrator=integrator,
                    gravity=(0, 0, -9.80665),
                    solver="newton",
                    iterations=100,
                    tolerance=1e-12,
                    disableflags=("eulerdamp",),
                ),
            ),
        )
        self.kp = self.tensor([[log.get("kp_encoded", log["kp"])] for log in logs])
        self.kd = self.tensor([[log.get("kd_encoded", log["kd"])] for log in logs])
        self.goal_speed = self.tensor([[log.get("goal_speed", 0)] for log in logs])
        self.feedforward = self.tensor([[log.get("feedforward_torque", 0)] for log in logs])
        self.initial_q = self.tensor([[log["entries"][0]["position"]] for log in logs])
        self.initial_v = self.tensor([[log["entries"][0].get("speed", 0)] for log in logs])
        self.initial_goal = self.tensor([[log["entries"][0]["goal_position"]] for log in logs])
        self.delay = TorchFractionalDelay(params.command_delay, dt, self.initial_goal)
        self.reset()

    def tensor(self, value):
        return torch.as_tensor(value, dtype=torch.float32, device=self.device)

    def reset(self, env_ids=None):
        self.sim.reset(env_ids)
        ids = slice(None) if env_ids is None else env_ids
        self.sim.data.qpos[ids] = self.initial_q[ids]
        self.sim.data.qvel[ids] = self.initial_v[ids]
        self.delay.reset(self.initial_goal[ids], ids)
        self.sim.forward()

    def step(self, goal, enabled):
        target = self.delay.push(goal)
        nominal = torch.clamp(
            self.kp * (target - self.sim.data.qpos[...])
            + self.kd * (self.goal_speed - self.sim.data.qvel[...])
            + self.feedforward,
            self.params.torque_min,
            self.params.torque_max,
        )
        torque = nominal * self.params.torque_ratio * enabled
        self.sim.data.ctrl[:] = torque
        self.sim.step()
        return nominal, torque, target

    def rollout(self):
        self.reset()
        lengths = [len(log["entries"]) for log in self.logs]
        max_len, n = max(lengths), len(self.logs)
        goals = np.zeros((max_len, n, 1), dtype=np.float32)
        enables = np.zeros_like(goals)
        for i, log in enumerate(self.logs):
            for key, destination in (("goal_position", goals), ("torque_enable", enables)):
                values = np.array([e[key] for e in log["entries"]])
                destination[: lengths[i], i, 0] = values
                destination[lengths[i] :, i, 0] = values[-1]
        goals, enables = self.tensor(goals), self.tensor(enables)
        output = torch.empty((max_len, n, 5), dtype=torch.float32, device=self.device)
        for k in range(max_len):
            output[k, :, 0] = self.sim.data.qpos[:, 0]
            output[k, :, 1] = self.sim.data.qvel[:, 0]
            for substep in range(self.substeps):
                values = self.step(goals[k], enables[k])
                if substep == 0:
                    for column, value in enumerate(values, start=2):
                        output[k, :, column] = value[:, 0]
        array = output.cpu().numpy().astype(float)
        if not np.all(np.isfinite(array)):
            raise FloatingPointError("Non-finite mjlab rollout")
        return [array[: lengths[i], i].copy() for i in range(n)]


def fixture_key(log):
    return tuple(
        log[k] for k in ("mass", "arm_mass", "length", "arm_com", "arm_inertia", "hub_inertia")
    )


def rollout_batch(
    logs: list[dict],
    params: M1Parameters,
    dt: float,
    *,
    xml_factory=pendulum_xml,
    integrator="euler",
):
    groups = {}
    for i, log in enumerate(logs):
        groups.setdefault(fixture_key(log), []).append(i)
    result = [None] * len(logs)
    for indices in groups.values():
        batch = MjlabPendulumBatch(
            [logs[i] for i in indices], params, dt, xml_factory=xml_factory, integrator=integrator
        )
        for i, prediction in zip(indices, batch.rollout(), strict=True):
            result[i] = prediction
        del batch
    return result

"""Frozen BAM M1 parameters in native MuJoCo physics (no fitted-parameter edits).

Only goal position is delayed, as in the identified BAM model. Enable is immediate.
The fixture offset belongs to pendulum geometry, never the robot actuator law.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import mujoco
import numpy as np

from motor_identification.rigs.pendulum import Pendulum


@dataclass(frozen=True)
class M1Parameters:
    torque_ratio: float
    armature: float
    q_offset: float
    command_delay: float
    friction_base: float
    friction_viscous: float
    torque_min: float
    torque_max: float

    @classmethod
    def load(cls, path: Path):
        values = json.loads(Path(path).read_text())
        if values["model"] != "m1" or values["motor_spec"]["family"] not in {"robstride", "damiao"}:
            raise ValueError("Expected a torque-MIT M1 snapshot")
        fields = {k: values[k] for k in cls.__dataclass_fields__ if not k.startswith("torque_m")}
        fields.update(
            torque_min=values["motor_spec"]["torque"][0],
            torque_max=values["motor_spec"]["torque"][1],
        )
        result = cls(**fields)
        if not all(np.isfinite(list(fields.values()))):
            raise ValueError("M1 parameters must be finite")
        if (
            min(
                result.armature, result.command_delay, result.friction_base, result.friction_viscous
            )
            < 0
            or result.torque_ratio <= 0
        ):
            raise ValueError("Invalid physical M1 parameters")
        return result


class FractionalDelay:
    """Causal fixed-step ring buffer; reset can isolate selected environments."""

    def __init__(self, delay: float, dt: float, initial):
        if not np.isfinite(delay) or delay < 0 or not np.isfinite(dt) or dt <= 0:
            raise ValueError("Expected finite delay >= 0 and dt > 0")
        steps = delay / dt
        self.whole = int(np.floor(steps))
        self.fraction = steps - self.whole
        self.buffer = np.broadcast_to(
            np.asarray(initial, dtype=float), (self.whole + 2, *np.shape(initial))
        ).copy()
        self.index = 0

    def reset(self, initial, env_ids=...):
        self.buffer[:, env_ids] = initial

    def push(self, goal):
        self.buffer[self.index] = goal
        recent = self.buffer[(self.index - self.whole) % len(self.buffer)]
        older = self.buffer[(self.index - self.whole - 1) % len(self.buffer)]
        result = (1 - self.fraction) * recent + self.fraction * older
        self.index = (self.index + 1) % len(self.buffer)
        return result


def pendulum_xml(log: dict, params: M1Parameters, dt: float) -> str:
    """Use exact pivot inertia and mass moment from the recorded fixture.

    The equivalent rigid body's COM inertia follows the parallel-axis theorem.
    Its out-of-plane inertia is immaterial to this hinge, but stays physical.
    Dry friction uses a stiff native constraint, resolved within one step; the
    1e-4 regularization is explicitly retained, not an exact-sticking claim.
    """
    rig = Pendulum(log)
    mass = rig.mass + rig.arm_mass
    com = (rig.mass * rig.length + rig.arm_mass * rig.arm_com) / mass
    inertia = rig.compute_mass(0, 0) - mass * com**2
    if inertia <= 0 or dt <= 0:
        raise ValueError("Non-physical fixture inertia or timestep")
    return f'''<mujoco model="identified_rs05_pendulum">
      <compiler angle="radian" inertiafromgeom="false"/>
      <option timestep="{dt}" gravity="0 0 -9.80665" integrator="Euler"
              solver="Newton" iterations="100" tolerance="1e-12">
        <flag eulerdamp="disable"/>
      </option>
      <worldbody><body name="pendulum" pos="0 0 0.3">
        <joint name="pivot" type="hinge" axis="1 0 0" ref="{-params.q_offset}"
               armature="{params.armature}" damping="{params.friction_viscous}"
               frictionloss="{params.friction_base}"
               solreffriction="-1 {-1 / dt}" solimpfriction="0.9999 0.9999 0.001"/>
        <inertial mass="{mass}" pos="0 0 {-com}"
                  diaginertia="{inertia} {inertia} {min(inertia, 1e-6)}"/>
        <geom type="capsule" fromto="0 0 0 0 0 {-rig.length}" size="0.006"
              contype="0" conaffinity="0" rgba="0.15 0.4 0.8 1"/>
        <geom type="sphere" pos="0 0 {-rig.length}" size="0.018"
              contype="0" conaffinity="0" rgba="0.9 0.45 0.15 1"/>
      </body></worldbody>
      <actuator><motor name="rs05" joint="pivot" gear="1"/></actuator>
    </mujoco>'''


class PendulumReplay:
    """Full rollout, initialized once; commands held between recorded samples."""

    def __init__(
        self, log: dict, params: M1Parameters, dt: float | None = None, *, xml_factory=pendulum_xml
    ):
        self.log, self.params = log, params
        self.dt = log["dt"] if dt is None else dt
        self.substeps = round(log["dt"] / self.dt)
        if self.substeps < 1 or not np.isclose(self.substeps * self.dt, log["dt"]):
            raise ValueError("Physics timestep must divide the recording timestep")
        self.xml = xml_factory(log, params, self.dt)
        self.model = mujoco.MjModel.from_xml_string(self.xml)
        self.data = mujoco.MjData(self.model)
        self.kp = log.get("kp_encoded", log["kp"])
        self.kd = log.get("kd_encoded", log["kd"])
        self.reset()

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        first = self.log["entries"][0]
        self.data.qpos[0] = first["position"]
        self.data.qvel[0] = first.get("speed", 0.0)
        self.delay = FractionalDelay(self.params.command_delay, self.dt, first["goal_position"])
        mujoco.mj_forward(self.model, self.data)

    def step(self, goal: float, enabled: bool):
        target = float(self.delay.push(goal))
        p, d = self.params, self.data
        nominal = np.clip(
            self.kp * (target - d.qpos[0])
            + self.kd * (self.log.get("goal_speed", 0) - d.qvel[0])
            + self.log.get("feedforward_torque", 0),
            p.torque_min,
            p.torque_max,
        )
        d.ctrl[0] = nominal * p.torque_ratio if enabled else 0.0
        torque = float(d.ctrl[0])
        mujoco.mj_step(self.model, d)
        return nominal, torque, target

    def rollout(self):
        self.reset()
        output = np.empty((len(self.log["entries"]), 5))
        for k, entry in enumerate(self.log["entries"]):
            output[k, :2] = self.data.qpos[0], self.data.qvel[0]
            for substep in range(self.substeps):
                values = self.step(entry["goal_position"], entry["torque_enable"])
                if substep == 0:
                    output[k, 2:] = values
        if not np.all(np.isfinite(output)):
            raise FloatingPointError("Non-finite MuJoCo replay")
        return output

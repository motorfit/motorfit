"""Newton's SolverMuJoCo CPU path used by the local asRoBallet example.

This validates Newton model import, coordinates, controls and stepping. It is
not a claim of independent Featherstone physics: that solver does not implement
joint_friction in the installed Newton revision.
"""

import xml.etree.ElementTree as ET

import mujoco
import newton
import numpy as np
import warp as wp

from .mujoco import FractionalDelay, M1Parameters, pendulum_xml


class NewtonPendulumBatch:
    """Disconnected single-hinge systems, one per recording, with no contacts."""

    def __init__(
        self,
        logs: list[dict],
        params: M1Parameters,
        dt=0.002,
        *,
        xml_factory=pendulum_xml,
        integrator="euler",
    ):
        if integrator not in ("euler", "implicitfast"):
            raise ValueError("Expected euler or implicitfast integrator")
        if not logs or len({log["dt"] for log in logs}) != 1:
            raise ValueError("Expected logs on a shared recording timestep")
        self.logs, self.params, self.dt = logs, params, dt
        self.substeps = round(logs[0]["dt"] / dt)
        if self.substeps < 1 or not np.isclose(self.substeps * dt, logs[0]["dt"]):
            raise ValueError("Physics timestep must divide recording timestep")
        root = ET.fromstring(xml_factory(logs[0], params, dt))
        world, actuators = root.find("worldbody"), root.find("actuator")
        world.clear()
        actuators.clear()
        for i, log in enumerate(logs):
            part = ET.fromstring(xml_factory(log, params, dt))
            actuator = part.find("actuator/motor")
            for body in part.find("worldbody"):
                if body.tag not in ("body", "geom"):
                    continue
                pos = np.fromstring(body.get("pos", "0 0 0"), sep=" ")
                pos[0] += i
                body.set("pos", " ".join(map(str, pos)))
                for element in body.iter():
                    if "name" in element.attrib:
                        element.set("name", f"{element.get('name')}_{i}")
                world.append(body)
            actuator.set("name", f"rs05_{i}")
            actuator.set("joint", f"pivot_{i}")
            actuators.append(actuator)
        self.xml = ET.tostring(root, encoding="unicode")
        with wp.ScopedDevice("cpu"):
            # Newton's default gravity is 9.81; importing MJCF does not replace it.
            builder = newton.ModelBuilder(gravity=(0, 0, -9.80665))
            newton.solvers.SolverMuJoCo.register_custom_attributes(builder)
            builder.add_mjcf(self.xml, ctrl_direct=True, ignore_inertial_definitions=False)
            self.model = builder.finalize()
            self.solver = newton.solvers.SolverMuJoCo(
                self.model,
                use_mujoco_cpu=True,
                disable_contacts=True,
                integrator=integrator,
                solver="newton",
                iterations=100,
                tolerance=1e-12,
            )
            self.state, self.next_state = self.model.state(), self.model.state()
            self.control = self.model.control()
        self.mj_model, self.mj_data = self.solver.mj_model, self.solver.mj_data
        if self.model.joint_coord_count != len(logs) or self.model.joint_dof_count != len(logs):
            raise ValueError("Newton import did not preserve independent single hinges")
        self.refs = self.model.mujoco.dof_ref.numpy().astype(float)
        np.testing.assert_allclose(self.refs, -params.q_offset, atol=1e-9)
        self.kp = np.array([log.get("kp_encoded", log["kp"]) for log in logs])
        self.kd = np.array([log.get("kd_encoded", log["kd"]) for log in logs])
        self.goal_speed = np.array([log.get("goal_speed", 0) for log in logs])
        self.feedforward = np.array([log.get("feedforward_torque", 0) for log in logs])
        self.reset()

    def reset(self):
        q = np.array([log["entries"][0]["position"] for log in self.logs])
        v = np.array([log["entries"][0].get("speed", 0) for log in self.logs])
        initial = np.array([log["entries"][0]["goal_position"] for log in self.logs])
        # Newton q is displacement from MJCF ref, while measurements use qpos.
        self.state.joint_q.assign((q - self.refs).astype(np.float32))
        self.state.joint_qd.assign(v.astype(np.float32))
        newton.eval_fk(self.model, self.state.joint_q, self.state.joint_qd, self.state)
        self.next_state.joint_q.assign(self.state.joint_q)
        self.next_state.joint_qd.assign(self.state.joint_qd)
        self.control.mujoco.ctrl.zero_()
        mujoco.mj_resetData(self.mj_model, self.mj_data)
        self.delay = FractionalDelay(self.params.command_delay, self.dt, initial)

    def position(self):
        return self.state.joint_q.numpy().astype(float) + self.refs

    def velocity(self):
        return self.state.joint_qd.numpy().astype(float)

    def step(self, goal, enabled):
        target = self.delay.push(goal)
        nominal = np.clip(
            self.kp * (target - self.position())
            + self.kd * (self.goal_speed - self.velocity())
            + self.feedforward,
            self.params.torque_min,
            self.params.torque_max,
        )
        torque = nominal * self.params.torque_ratio * enabled
        # Persist the value actually sent across Newton's float32 control boundary.
        torque = torque.astype(np.float32)
        self.control.mujoco.ctrl.assign(torque)
        self.state.clear_forces()
        self.solver.step(self.state, self.next_state, self.control, None, self.dt)
        self.state, self.next_state = self.next_state, self.state
        return nominal, torque, target

    def rollout(self):
        self.reset()
        lengths = [len(log["entries"]) for log in self.logs]
        max_len, n = max(lengths), len(self.logs)
        goals = np.zeros((max_len, n))
        enables = np.zeros_like(goals, dtype=bool)
        for i, log in enumerate(self.logs):
            for key, destination in (("goal_position", goals), ("torque_enable", enables)):
                values = np.array([e[key] for e in log["entries"]])
                destination[: lengths[i], i] = values
                destination[lengths[i] :, i] = values[-1]
        output = np.empty((max_len, n, 5))
        for k in range(max_len):
            output[k, :, 0], output[k, :, 1] = self.position(), self.velocity()
            for substep in range(self.substeps):
                values = self.step(goals[k], enables[k])
                if substep == 0:
                    output[k, :, 2:] = np.array(values).T
        if not np.all(np.isfinite(output)):
            raise FloatingPointError("Non-finite Newton rollout")
        return [output[: lengths[i], i].copy() for i in range(n)]


def rollout_batch(
    logs: list[dict],
    params: M1Parameters,
    dt: float,
    *,
    xml_factory=pendulum_xml,
    integrator="euler",
):
    return NewtonPendulumBatch(
        logs, params, dt, xml_factory=xml_factory, integrator=integrator
    ).rollout()

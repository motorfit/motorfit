"""Rigid-body pendulum geometry, independent of the motor and fitter."""

import numpy as np


class Pendulum:
    """Point load, arm and hub; all inertias are about the motor pivot."""

    def __init__(self, metadata: dict):
        self.mass = metadata["mass"]
        self.arm_mass = metadata["arm_mass"]
        self.length = metadata["length"]
        self.arm_com = metadata.get("arm_com", self.length / 2)
        self.arm_inertia = metadata.get("arm_inertia", self.arm_mass * self.length**2 / 3)
        self.hub_inertia = metadata.get("hub_inertia", 0.0)

    def compute_mass(self, q, dq):
        return self.mass * self.length**2 + self.arm_inertia + self.hub_inertia

    def compute_bias(self, q, dq):
        moment = self.mass * self.length + self.arm_mass * self.arm_com
        return -9.80665 * moment * np.sin(q)

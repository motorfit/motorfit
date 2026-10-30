"""Recorded effort adapter: fit the plant without inventing a firmware PD law."""

import numpy as np
from bam.actuator import Actuator
from bam.simulate import fractional_delay_shift

from .actuator import MITActuator


class RecordedEffortActuator(MITActuator):
    """One saved nominal-Nm input per BAM step, including vectorized batches.

    torque_ratio refines the nominal command scale (for MyActuator this is the
    profile's output-side Nm/A prior). command_delay shifts the saved effort,
    not a recomputed goal. reset_period resets plant state, never the input clock.
    """

    stateful = True

    def load_log(self, log):
        Actuator.load_log(self, log)
        if not np.all(np.asarray(log.get("control_source")) == "recorded_effort"):
            raise ValueError("Effort actuator requires control_source=recorded_effort")
        try:
            controls = np.stack([e["control"] for e in log["entries"]])
        except KeyError as exc:
            raise ValueError("Effort actuator requires the actual recorded control") from exc
        if not np.isfinite(controls).all():
            raise ValueError("Nonfinite recorded effort")
        dt = float(np.asarray(log["dt"]).reshape(-1)[0])
        self.controls = fractional_delay_shift(controls, self.model.command_delay.value, dt)
        self.index = 0

    def compute_control(self, q_target, q, dq, dt):
        if self.index >= len(self.controls):
            raise RuntimeError("Recorded effort exhausted; load_log before each rollout")
        control = self.controls[self.index]
        self.index += 1
        return control

    def get_state(self):
        return self.index

    def set_state(self, state):
        self.index = state

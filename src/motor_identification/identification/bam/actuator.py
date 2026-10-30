"""Torque-based MIT control adapter for the upstream BAM fitter."""

from functools import partial

from bam.actuator import Actuator, ArrayLike
from bam.actuators import actuators
from bam.parameter import Parameter

from motor_identification.devices.spec import MotorSpec
from motor_identification.rigs.pendulum import Pendulum


class MITActuator(Actuator):
    """MIT PD using the model's nominal torque range and recorded commands.

    ``torque_ratio`` maps nominal PD torque into effective torque. This model
    does not separately identify electrical kt/R or model voltage saturation.
    Its nominal clamp uses the protocol range as a prior, not a measured drive
    limit. Velocity/feedforward metadata retain encoded zero offsets.
    """

    def __init__(self, spec: MotorSpec):
        super().__init__(Pendulum)
        self.spec = spec

    def initialize(self):
        # Shared numerical priors, not measured properties of any motor model.
        # BAM --set can hold either parameter at a separately measured value.
        self.model.torque_ratio = Parameter(1.0, 0.1, 3.0)
        self.model.armature = Parameter(1e-4, 0.0, 0.02)

    def load_log(self, log: dict):
        super().load_log(log)
        self.kp = log.get("kp_encoded", log["kp"])
        self.kd = log.get("kd_encoded", log["kd"])
        self.goal_speed = log.get("goal_speed", 0.0)
        self.feedforward_torque = log.get("feedforward_torque", 0.0)

    def control_unit(self) -> str:
        return "Nm"

    def compute_control(
        self, q_target: ArrayLike, q: ArrayLike, dq: ArrayLike, dt: float
    ) -> ArrayLike:
        nominal_torque = (
            self.kp * (q_target - q) + self.kd * (self.goal_speed - dq) + self.feedforward_torque
        )
        return self.backend.clamp(nominal_torque, *self.spec.torque)

    def compute_torque(
        self, control: ArrayLike | None, torque_enable, q: ArrayLike, dq: ArrayLike
    ) -> ArrayLike:
        nominal_torque = 0.0 if control is None else control
        return nominal_torque * self.model.torque_ratio.value * torque_enable

    def get_extra_inertia(self) -> float:
        return self.model.armature.value


def register(spec: MotorSpec) -> None:
    """Extend BAM's shared registry without replacing its dictionary."""
    if spec.recorded_effort:
        from .effort import RecordedEffortActuator

        actuators[spec.name] = partial(RecordedEffortActuator, spec)
    else:
        actuators[spec.name] = partial(MITActuator, spec)


# Keep existing imports working; recorded RS05 numerics are unchanged.
RobStrideActuator = MITActuator

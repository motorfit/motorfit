# Models and parameters

MotorFit fits a mechanical actuator model from position trajectories. The fixture
geometry and controller gains are inputs; the optimizer adjusts model parameters
so simulated position matches the recordings.

## The controller and pendulum

RobStride and Damiao use the same torque-MIT model in the fitter:

$$
\tau_\mathrm{nom}=\operatorname{clip}\!\left[
K_p\bigl(q_d(t-d)-q\bigr)+K_d(\dot q_d-\dot q)+\tau_\mathrm{ff},\;
\tau_\min,\tau_\max\right],
$$

$$
\tau_\mathrm{motor}=e\,r\,\tau_\mathrm{nom}.
$$

Here `e` is the recorded torque-enable state, `r` is `torque_ratio`, and `d` is
`command_delay`. The limits come from the recorded motor profile. Encoded gains,
velocity target and feedforward torque are used when present, preserving
quantization offsets even for a requested zero.

Only the position target receives the identified delay. Disabling torque acts
immediately in this model. The delay is fitted from motion; it is not a direct
measurement of CAN round-trip time or power-stage shutdown.

For the pendulum, total inertia is the known fixture inertia plus `armature`.
Gravity depends on the measured mass moment and `q + q_offset`.
The [setup guide](../guide/configuration.md#3-measure-the-fixture) gives the fixture
equations and units.

## M1 parameters

M1 has six fitted parameters:

| Parameter | Unit | Meaning | Search interval |
|---|---|---|---|
| `torque_ratio` | dimensionless | Multiplier from nominal command torque to effective motor torque | 0.1–3 |
| `armature` | kg·m² | Added motor/drive inertia at the modeled output joint | 0–0.02 |
| `q_offset` | rad | Residual angular offset in the fixture's gravity model | −0.1–0.1 |
| `command_delay` | s | Delay applied to the position command | 0–0.05 |
| `friction_base` | N·m | Coulomb-like friction limit | 0–0.2 |
| `friction_viscous` | N·m·s/rad | Speed-proportional friction coefficient | 0–1 |

These are the current optimizer search intervals, not measured hardware limits.
The MotorFit adapter defines the first two; the pinned BAM model defines the
remaining four.

For M1, the resisting-torque budget is
`friction_base + friction_viscous × abs(speed)`. BAM clips the applied friction to
the torque needed to stop the joint in a step. This permits sticking near zero
speed instead of forcing a sign-based friction torque through a velocity reversal.

The parameters describe the observed system together. For example, an incorrect
tip inertia can change the fitted `armature` or torque scale. `torque_ratio` does
not independently identify winding torque constant, resistance, voltage saturation
or torque-sensor calibration.

## Model families

All six families include the controller, inertia, offset, delay and viscous term.
They differ in the friction model:

| Family | Added friction behavior |
|---|---|
| `m1` | Constant Coulomb-like friction |
| `m2` | M1 plus a Stribeck increase near zero speed |
| `m3` | M1 plus friction depending on load torque |
| `m4` | Load dependence combined with Stribeck behavior |
| `m5` | Separate motor-side and external-side load terms, with Stribeck behavior |
| `m6` | M5 plus quadratic load terms in the supported opposing-torque regime |

Stribeck models add `friction_stribeck`, the characteristic velocity
`dtheta_stribeck`, and shape exponent `alpha`. Load-dependent families add their
corresponding load coefficients. The exact parameter list is saved in each model
JSON; the implementation is in BAM's `bam/model.py`.

More parameters require data that distinguishes their effects. Compare families
on the same validation runs rather than selecting the lowest training score.

## Reading a saved model

`model.json` includes `model`, `actuator`, `motor_spec`, the parameter values and,
for new fits, an `identification` score object. Load it through MotorFit so that the
saved motor definition is registered with BAM:

```python
from motorfit.identification.bam import load_model

model = load_model("data/my-motor/selected/model.json")
for name, parameter in model.get_parameters().items():
    print(name, parameter.value)
```

Editing a current profile TOML does not change the snapshot saved with an existing
model. [Data formats](data.md) describes the related recording fields.

## Using the model in simulation

The included M1 pendulum adapters map three mechanical parameters directly:

| Identified value | MuJoCo joint property |
|---|---|
| `armature` | `armature` |
| `friction_base` | `frictionloss` |
| `friction_viscous` | `damping` |

`torque_ratio` and `command_delay` belong in the controller calculation. Reproduce
the command clamp, scaling and delay in the same order as the equations above.
The pendulum adapter represents `q_offset` through the hinge reference; in a robot,
first relate this bench offset to the robot's own joint coordinate convention.

Changing those three XML attributes alone does not reproduce the entire model.
MotorFit generates replay scenes for the pendulum and leaves robot integration to
the caller. Compare the integrated controller against held-out recordings before
using it for a wider operating range.

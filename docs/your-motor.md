# Bring your own motor

Choose the [connection path](motors.md) from the controller protocol and control law. RobStride and Damiao have native acquisition adapters for the torque-based MIT law. MyActuator, HighTorque and Hexfellow use independent effort drivers and a recorded-input BAM adapter; follow [their workflow](effort-motors.md).

## Configure the mounted assembly

Copy a setup inside [`configs/setups/`](https://github.com/motorfit/motorfit/tree/main/configs/setups) so its references stay valid. Use `rs05_pendulum.toml` for RobStride or `dm4310_pendulum.toml` for Damiao, then edit:

| Input | What to measure or select |
|---|---|
| Motor profile | Exact model, protocol mapping and firmware; profiles are in `configs/motors/<family>/` |
| Device | CAN channel, motor address, feedback/host address and timeout |
| Fixture | Tip mass, length, arm mass, center of mass, inertia and hub inertia |
| Acquisition | Excitation, amplitude, duration, sample rate and fixed gains |
| Supply | Configured voltage; this is not a synchronous voltage measurement |
| Coordinate | A distinct ignored file for this mounted device's software zero |

Read and inspect the device, then establish the coordinate at a known physical angle. The supplied gains and fixture describe examples, not commissioned settings for another assembly. [Acquisition](acquisition.md) gives the command sequence.

The fitter uses the full motor definition saved in each recording. A new compatible model name does not require a new friction model. Protocol ranges are encoding limits, not measured output-torque limits. Damiao runtime PMAX/VMAX/TMAX must match the profile.

## Extend a protocol or control law

| Boundary | Implementation |
|---|---|
| Motor specification | [`MotorSpec`](https://github.com/motorfit/motorfit/blob/main/src/motor_identification/devices/spec.py) |
| Native backend selection and command quantization | [`registry.py`](https://github.com/motorfit/motorfit/blob/main/src/motor_identification/devices/registry.py) |
| Device lifecycle and wire evidence | [`devices/`](https://github.com/motorfit/motorfit/tree/main/src/motor_identification/devices) |
| Recording schema and command timing | [`recorder.py`](https://github.com/motorfit/motorfit/blob/main/src/motor_identification/acquisition/recorder.py) |
| BAM input-to-torque law | [`MITActuator`](https://github.com/motorfit/motorfit/blob/main/src/motor_identification/identification/bam/actuator.py) / [`RecordedEffortActuator`](https://github.com/motorfit/motorfit/blob/main/src/motor_identification/identification/bam/effort.py) |
| Saved model/log loading | [`runner.py`](https://github.com/motorfit/motorfit/blob/main/src/motor_identification/identification/bam/runner.py) |
| Frozen M1 physics replay | [`identification/`](https://github.com/motorfit/motorfit/tree/main/src/motor_identification/identification) |

Add an adapter only after specifying actual units, gains, saturation, enable/fault state and fresh feedback semantics. An interface named `send_mit` does not guarantee the same law: [the support matrix](motors.md) documents the reference protocols’ differences. The snapshot selects either the torque-MIT law or the recorded-effort adapter. Unrecognized families are rejected.

Keep device codecs and transports separate from the numerical model. Test wire fixtures, shutdown failures and an offline process/fit/load cycle, then collect a small real dataset and evaluate independent runs before making accuracy claims.

## Use another fixture

[`Pendulum`](https://github.com/motorfit/motorfit/blob/main/src/motor_identification/rigs/pendulum.py) supplies the current inertia and gravity terms. Measure its inputs independently of the motor fit. A fixture with different equations needs a rig implementation and a matching simulation scene. `MITActuator` currently selects `Pendulum`; a different rig requires explicit adapter wiring.

The archived `data/rs05/assets/bench/` is the reference assembly's geometry. Do not treat its mass properties or appearance as measured geometry for a new device.

## Freeze a reusable result

Keep each motor's model and dataset in its own directory. Preserve its UID or identity, coordinates, controller settings and fixture with the recordings. Parameter JSON must retain the full motor definition. Never substitute the bundled RS05 M1 for a new motor's fit.

For a portable study, follow the [example manifest](https://github.com/motorfit/motorfit/blob/main/examples/offline/manifest.json): relative paths, explicit splits, model/recording hashes and reference predictions. The current plots use pendulum load labels such as `mass_g`; other rigs need corresponding presentation metadata. See the [workflow](workflow.md) for split and evaluation discipline.

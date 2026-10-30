# Architecture

MotorFit organizes the workflow around motor, controller, fixture and dataset boundaries. RS05-specific evidence lives in a [reference study](../case-studies/rs05.md).

The reusable device unit is a protocol family; the configuration unit is a motor model; the calibrated unit is a mounted device. RS00–RS06 share one RobStride driver; Damiao MIT uses a separate native driver. MyActuator, HighTorque and Hexfellow have independent effort drivers.

| Directory | Responsibility |
|---|---|
| `src/motorfit/devices/` | Native protocols, backend selection and supported-model catalogue |
| `acquisition` | Generic Python recorder, trajectories, formal CSV-to-BAM export |
| `identification/bam` | MIT-law / recorded-effort adapters and unchanged upstream BAM integration |
| `identification/{mujoco,newton,mjlab}.py` | Frozen M1 replay on optional backends |
| `rigs` | Recorded pendulum geometry and CAD mass properties |
| `dataset.py` | Relative paths, content hashes, motor identity and split checks |
| `validation` | Feedback audit, stationary evidence, solver options and release events |
| `scripts` | CAD preparation, measured-data figure generation and replay rendering |

A setup in `configs/setups/` composes model profiles from `motors/`, measured geometry from `fixtures/` and experiment settings from `acquisition/`. References resolve against that setup file. Each mounted device has its own ignored coordinate file in `configs/local/`. `configs/simulation/` contains reusable solver settings; measured release scenes belong to the local study archive. Loading a model or an offline dataset does not access the device driver.

Dataset schema 1 has a `records` list. Every recording names its processed/raw file and BAM reference prediction with SHA-256, plus optional original frame files. All current paths resolve relative to the manifest. Historical absolute paths inside unchanged raw JSON are evidence only: executable readers never use them as file locations.

The full dataset and the three-record example share this schema. The formal split and UID travel with the data; arbitrary changes to a current TOML cannot reinterpret a saved recording or M1. `motorfit verify` verifies the model and all named inputs.

Add a motor of the same protocol by adding a sourced model TOML and a separate setup. Add another protocol as a driver and a control-law adapter. Add another fixture as configuration, or a new rig implementation if its physical equations differ.

The registry selects five native driver families. RobStride and Damiao use the torque-MIT actuator; MyActuator, HighTorque and Hexfellow use host PD acquisition and the recorded-effort BAM adapter. Both select the measured pendulum rig; see [motor support](../reference/motors.md). These boundaries prevent an SDK method name from silently implying compatible units or fresh measurement timing.

The installed command is `motorfit`; Python modules live under `motorfit`. All acquisition goes through `motorfit record`. The C++ helper in `validation/release_event.cpp` is used only for MuJoCo event replay.

## Extension points

### Motor drivers and control laws

| Boundary | Implementation |
|---|---|
| Motor specification | [`MotorSpec`](https://github.com/motorfit/motorfit/blob/main/src/motorfit/devices/spec.py) |
| Native backend selection and command quantization | [`registry.py`](https://github.com/motorfit/motorfit/blob/main/src/motorfit/devices/registry.py) |
| Device lifecycle and wire evidence | [`devices/`](https://github.com/motorfit/motorfit/tree/main/src/motorfit/devices) |
| Recording schema and command timing | [`recorder.py`](https://github.com/motorfit/motorfit/blob/main/src/motorfit/acquisition/recorder.py) |
| BAM input-to-torque law | [`MITActuator`](https://github.com/motorfit/motorfit/blob/main/src/motorfit/identification/bam/actuator.py) / [`RecordedEffortActuator`](https://github.com/motorfit/motorfit/blob/main/src/motorfit/identification/bam/effort.py) |
| Saved model/log loading | [`runner.py`](https://github.com/motorfit/motorfit/blob/main/src/motorfit/identification/bam/runner.py) |
| Frozen M1 physics replay | [`identification/`](https://github.com/motorfit/motorfit/tree/main/src/motorfit/identification) |

Add an adapter only after specifying actual units, gains, saturation, enable/fault state and fresh feedback semantics. An interface named `send_mit` does not guarantee the same law: [the support matrix](../reference/motors.md) documents the reference protocols’ differences. The snapshot selects either the torque-MIT law or the recorded-effort adapter. Unrecognized families are rejected.

Keep device codecs and transports separate from the numerical model. Test wire fixtures, shutdown failures and an offline process/fit/load cycle, then collect a small real dataset and evaluate independent runs before making accuracy claims.

### Fixtures

[`Pendulum`](https://github.com/motorfit/motorfit/blob/main/src/motorfit/rigs/pendulum.py) supplies the current inertia and gravity terms. Measure its inputs independently of the motor fit. A fixture with different equations needs a rig implementation and a matching simulation scene. `MITActuator` currently selects `Pendulum`; a different rig requires explicit adapter wiring.

The archived `data/rs05/assets/bench/` is the reference assembly's geometry. Do not treat its mass properties or appearance as measured geometry for a new device.

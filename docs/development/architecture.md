# Architecture

MotorFit connects bench acquisition to BAM identification and physics replay. The
main boundary is the saved recording: fitting reads its motor and fixture snapshot
without opening CAN or consulting a mounted device's current configuration.

## Data flow

```text
Setup TOML → native driver + trajectory → raw recording
                                             ↓ process
                                      uniform-grid logs
                                             ↓ fit
                                        model.json
                                             ↓ evaluate
                                  predictions and errors
```

Physics replay adds a packaging step: a dataset manifest names the model,
recordings and saved BAM predictions with relative paths and hashes. See
[Data formats](../reference/data.md) for the two input formats and their fields.

## Code map

Paths below are relative to `src/motorfit/`.

| Module | Responsibility |
|---|---|
| `cli.py` | Dispatches the `motorfit` commands |
| `config.py` | Composes setup, motor, fixture, motion and coordinate files |
| `devices/spec.py` | Defines model names, protocol families and encoding ranges |
| `devices/registry.py` | Selects a driver and applies command quantization |
| `devices/robstride/`, `devices/damiao/` | Encode frames, match feedback and manage device state |
| `acquisition/recorder.py` | Executes a trajectory, retains samples/frames and shuts down |
| `acquisition/trajectories.py` | Adapts BAM trajectories and implements `soccer_sweep` |
| `identification/bam/` | Registers the torque-MIT actuator and wraps BAM processing, fitting and evaluation |
| `rigs/pendulum.py` | Supplies fixture inertia and gravity |
| `identification/{mujoco,newton,mjlab}.py` | Replays the supported M1 pendulum model in each backend |
| `dataset.py` | Resolves manifest paths and checks hashes, identity and splits |
| `validation/` | Implements RS05 feedback audits, solver settings and release-event analysis |

Upstream BAM stays in `third_party/bam/` at the committed submodule revision.
MotorFit's integration belongs in its own package. The C++ helper
`validation/release_event.cpp` is used for MuJoCo event replay; ordinary Python
recording does not require it.

## Configuration and model identity

Three objects serve different purposes:

- A **protocol family** chooses the wire implementation, such as RobStride.
- A **model profile** defines a model's encoding ranges, such as RS05.
- A **mounted setup** adds device addresses, a measured fixture and a physical zero.

A setup composes those files using paths relative to the setup file. Mounted-device
coordinates live under ignored `configs/local/`. The resolved values travel with
each recording; the motor profile also travels with a fitted model.

The fitter requires matching motor snapshots across its inputs. Loads and gains
may differ between records. Editing a TOML later does not reinterpret an existing
log or saved model. Packaged replay additionally verifies the manifest's hashes,
UID and split information before using the data.

## Add a model using an existing protocol

1. Add a sourced profile under `configs/motors/<family>/`, with the actual encoding ranges.
2. Add a setup template referencing that profile and an appropriate fixture and motion file.
3. Check profile loading and representative wire encodings, then commission the physical unit.
4. Record and evaluate independent runs before documenting hardware accuracy.

RS00–RS06 share the RobStride driver. The Damiao MIT profiles share the Damiao
driver. A common frame layout does not imply common torque, speed or gain ranges.
[Protocols](../reference/protocols.md) identifies the source for each family.

## Add a protocol or control law

Implement the driver lifecycle and feedback interface alongside the existing
families, then register the family in `devices/registry.py`. Define command units,
gain semantics, saturation, enable state, faults and reply matching explicitly.

The current numerical adapter is
[`MITActuator`](https://github.com/motorfit/motorfit/blob/main/src/motorfit/identification/bam/actuator.py).
It reconstructs nominal torque from encoded position/velocity targets, gains and
feedforward torque. A protocol with a different control law needs its own adapter,
recorded inputs and saved-model loader support. An API method called `send_mit`
alone is insufficient to establish compatible behavior.

Verify representative expected bytes, failure cleanup and an offline
process/fit/load operation. Adding a BAM adapter does not automatically add support
to the M1 physics backends; implement and check those equations separately.

## Add a fixture

Change a pendulum's measured values through configuration. If its physical
equations differ, implement a rig that supplies the mass and bias terms and wire
it into the actuator. `MITActuator` currently selects `Pendulum` explicitly.
Physics replay also needs a corresponding scene and matching coordinate convention.

The RS05 CAD assembly under `data/rs05/assets/bench/` belongs to that archived
experiment. A new fixture needs its own measurements.

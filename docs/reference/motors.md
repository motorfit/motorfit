# Supported motors

MotorFit records **RobStride and Damiao** motors through Linux SocketCAN. Choose a
profile matching both the motor model and its firmware protocol, then use it in a
[bench setup](../guide/configuration.md).

| Family | Supported protocol | Starting setup |
|---|---|---|
| RobStride | Manufacturer private protocol over extended CAN | `configs/setups/rs05_pendulum.toml` |
| Damiao | MIT control over standard CAN | `configs/setups/dm4310_pendulum.toml` |

Both drivers support feedback reading, register inspection, software-zero capture
and trajectory recording. Their recordings use the same fitting workflow.

## RobStride profiles

The `configs/motors/robstride/` directory contains:

| Models | Profile files |
|---|---|
| RS00, RS01, RS02 | `rs00.toml`, `rs01.toml`, `rs02.toml` |
| RS03, RS04 | `rs03.toml`, `rs04.toml` |
| RS05, RS06 | `rs05.toml`, `rs06.toml` |

For example, an RS06 setup uses `../motors/robstride/rs06.toml` when the setup is
under `configs/local/`. Each model has its own position, velocity, torque and gain
encoding ranges. Do not substitute the RS05 profile merely because the wire format
is shared.

The RobStride driver targets the private extended-CAN protocol. Alternative
CANopen or MIT firmware layouts require a different adapter.

## Damiao profiles

Profiles live in `configs/motors/damiao/`:

| Model | Profile |
|---|---|
| DM3507 | `3507.toml` |
| DM4310 / DM4310P | `4310.toml` / `4310p.toml` |
| DM4340 / DM4340P | `4340.toml` / `4340p.toml` |
| DM4340X | `4340_v20.toml` |
| DM6006 | `6006.toml` |
| DM8006 / DM8009 | `8006.toml` / `8009.toml` |
| DM10010L / DM10010 | `10010l.toml` / `10010.toml` |
| H3510 / G6215 / H6220 | `h3510.toml` / `g6215.toml` / `h6220.toml` |
| JH11 / 6248P | `jh11.toml` / `6248p.toml` |

`4340_v20` is the repository's profile name for **DM4340X**. It is distinct from
the standard DM4340 profile. Before enabling, the driver checks the device's PMAX,
VMAX and TMAX against the selected profile.

Serial bridges and the DM_Device SDK transport are not implemented. Use a
SocketCAN-compatible adapter.

## What a profile contains

A profile stores the model name, family and command-encoding ranges in SI units.
These ranges describe the protocol; they are not identified friction, inertia or
rated continuous-torque values. Physical parameters come from an experiment and
are saved separately in `model.json`.

List the installed profiles and validation coverage with:

```bash
uv run --no-sync motorfit motors
uv run --no-sync motorfit motors --json
```

## Validation coverage

**RS05 has recorded hardware evidence** in [the reference study](../case-studies/rs05.md).
The other RobStride profiles and all Damiao profiles require commissioning on the
actual unit. Software tests check protocol encoding, response matching, startup
checks, error cleanup and the offline fitting path; they do not establish accuracy
on every motor listed above.

Continue with [Setup](../guide/configuration.md) to configure a mounted device.
For wire formats, register behavior and manufacturer sources, see [Protocols](protocols.md).

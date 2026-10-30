# Motor support

MotorFit implements native SocketCAN acquisition for **RobStride, Damiao, MyActuator, HighTorque and Hexfellow**, with saved command/feedback evidence and adapters for BAM identification.

## Native support

| Family | Shipped profile identifiers | Acquisition → BAM | Hardware evidence |
|---|---|---|---|
| RobStride | `rs00`, `rs01`, `rs02`, `rs03`, `rs04`, `rs05`, `rs06` | Implemented for private extended CAN | RS05 reference study; other profiles unverified on hardware |
| Damiao | `3507`, `4310`, `4310p`, `4340`, `4340p`, `4340_v20`, `6006`, `8006`, `8009`, `10010l`, `10010`, `h3510`, `g6215`, `h6220`, `jh11`, `6248p` | Implemented for MIT over SocketCAN | Offline protocol and pipeline tests only |

The Damiao identifiers correspond to DM3507, DM4310, DM4310P, DM4340, DM4340P, DM4340X, DM6006, DM8006, DM8009, DM10010L, DM10010, H3510, G6215, H6220, JH11 and 6248P. Profile `4340_v20` is the existing identifier for the **4340X** template; do not substitute the standard 4340 mapping.

Profiles define protocol encoding ranges, not rated continuous torque, commissioned limits or identified physical parameters. Match the actual model and firmware, measure the fixture, and identify each mounted device. Hexfellow uses CAN-FD; the other families use classic CAN. Serial/DM_Device bridges and alternative RobStride CiA402/MIT firmware protocols are not implemented here.

```bash
uv run --frozen motorfit motors
uv run --frozen motorfit motors --json
```

## Current and torque protocols

| Family | Protocol templates | Acquisition and identification |
|---|---|---|
| MyActuator | `rmd_x_v3` | A1 current commands; configured output Nm/A, multi-turn angle, measured current; recorded-effort BAM adapter |
| HighTorque | `ht_can` | Pure torque 05/13; 17/01 sensor requests; recorded-effort BAM adapter |
| Hexfellow | `canopen_v07`, `canopen_v08` | CANopen torque mode 4; addressed SDO over CAN-FD; firmware and peak-torque readback; recorded-effort BAM adapter |

[Complete setup, record, process, fit and evaluate commands](../guide/effort-control.md). These are protocol templates, not a list of hardware-tested model variants. New templates deliberately use experiment limits instead of guessed vendor model specifications.

All three have independent Python implementations and offline end-to-end tests. M1–M6 analytical BAM fitting/evaluation/plotting is supported; the existing MuJoCo/Newton/mjlab firmware-controller replay remains limited to torque-MIT models. Only RS05 has real reference data.

## Damiao acquisition

Copy [`dm4310_pendulum.toml`](https://github.com/motorfit/motorfit/blob/main/configs/setups/dm4310_pendulum.toml) in the same directory. Select a profile from [`configs/motors/damiao`](https://github.com/motorfit/motorfit/tree/main/configs/motors/damiao), then set the actual fixture, supply, CAN address, feedback address and trajectory. The example gains and fixture are placeholders for a measured assembly.

```bash
uv run --frozen motorfit inspect --setup configs/setups/dm4310_pendulum.toml \
  --out outputs/dm4310-inspection.json
uv run --frozen motorfit zero --setup configs/setups/dm4310_pendulum.toml --angle 0
uv run --frozen motorfit record --setup configs/setups/dm4310_pendulum.toml \
  --out outputs/dm4310-run
uv run --frozen motorfit process --raw outputs/dm4310-run \
  --out outputs/dm4310-processed --dt 0.01
```

`zero` assumes the pendulum has been placed at the given physical angle. It stores a software offset. `record` executes motion. Follow [identification](../guide/identification.md) to collect multiple runs, separate train/validation/test data, and fit the recorded model. The RS05 frozen parameters must not be reused as identified Damiao parameters.

Before enabling, the driver stops the motor and checks **PMAX/VMAX/TMAX** against the profile. A mismatch aborts. It verifies MIT mode and watchdog register writes through acknowledgements and readbacks. The driver writes the TIMEOUT register as `round(watchdog_ms × 20)` ticks. No firmware zero, fault-clear or persistent-save command is issued.

Position uses 16-bit encoding; velocity, torque, Kp and Kd use 12 bits. The recorded `*_encoded`, `goal_speed` and `feedforward_torque` values preserve their quantized values, including nonzero representations of nominal zero. BAM uses these values. Wire status is retained as `status_code`; `mode` is normalized to 0=disabled, 2=enabled. `load` is nominal protocol torque in Nm, not an independently calibrated torque measurement.

Each transaction drains queued frames, logs all frames and accepts only the configured feedback CAN ID and motor nibble. A fault, unexpected enable state or missing response aborts recording and attempts disable. As in RobStride, the protocol has no sequence number; this does not prove that a delayed packet cannot arrive after a new request. The host sampling timestamp is reception time, not a motor-side measurement clock.

## Sources and validation

See the [manufacturer protocol references](protocols.md) for framing, register access and firmware control modes. The source links in the profiles point to protocol documentation. Profile numbers are encoding templates and must be checked against the mounted device; they are not identified parameters or evidence of hardware validation. RS01/02/05/06 keep their existing pinned manuals and 16-bit codec. RS00/03/04 retain their current mapping ranges and model-specific gain limits, pending firmware/hardware verification.

Tests exercise native current/torque frame packing, firmware-specific units, recorded-effort timing, Damiao frame packing, addressing, register readback, range mismatch, missing replies, fault/disable handling, interruption and the full offline BAM process/fit/load path. Only RS05 has recorded hardware validation; the remaining profiles require commissioning on the mounted device.

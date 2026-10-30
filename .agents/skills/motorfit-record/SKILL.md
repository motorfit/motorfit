---
name: motorfit-record
description: Configure a mounted motor and collect MotorFit bench recordings. Use when selecting a motor profile, establishing its software coordinate, inspecting a device, or recording excitation trajectories.
---

# Record a motor

Run commands from the MotorFit repository root. Start with [bring your own motor](../../../docs/your-motor.md) and the [support matrix](../../../docs/motors.md), then read the acquisition guide for the selected control path.

## Prepare the mounted assembly

- Identify the exact model and firmware, CAN channel and addresses, supply setting, measured fixture, excitation, gains, limits and sampling rate. Copy the matching setup from [configs/setups](../../../configs/setups) and adjust its referenced files. References resolve against the setup file, so preserve or update them when moving it.
- Give this mounted device its own ignored coordinate file under `configs/local/`. Never copy another assembly's encoder offset or assume that a template contains a calibrated zero. Changing weights alone does not require recalibrating an unchanged mounting.
- For RobStride and Damiao, follow [acquisition.md](../../../docs/acquisition.md). Damiao runtime PMAX/VMAX/TMAX must match its profile.
- For MyActuator, HighTorque and Hexfellow, follow [effort-motors.md](../../../docs/effort-motors.md) before connecting. Resolve MyActuator's placeholder Nm/A scale and current limit; check HighTorque's exact feedback ID and externally configured drive timeout; match Hexfellow's 07/08 firmware and CAN-FD timing. These use host PD and recorded effort, with different feedback timing from onboard MIT control.

When a required measurement or device setting is missing, prepare the configuration and ask for that specific input before dependent hardware work. Do not invent a fixture mass, zero, address or torque scale. Honor existing authorization; a setup-only request does not authorize enabling motion. Before recording, establish that the configured movement and physical assembly are ready. MyActuator recording also changes its persistent B3 timeout and releases its brake, as described in the effort guide.

## Inspect, establish coordinates and record

After preparing the actual setup, set `SETUP` to its path. Use a fresh recording destination for each run.

```bash
uv run --frozen motorfit read --setup "$SETUP"
uv run --frozen motorfit inspect --setup "$SETUP" --out outputs/my-motor/inspection.json
```

These commands do not enable the motor. Keep an existing verified zero. If a new coordinate is needed, have the mechanism physically placed at a known angle before running `motorfit zero --setup "$SETUP" --angle <radians>`. Downward is physical zero with encoder-positive direction; this command saves a software offset and does not move the mechanism.

Once the recording inputs and physical readiness are established:

```bash
uv run --frozen motorfit record --setup "$SETUP" --out outputs/my-motor/raw/train/run-01
```

Choose duration and amplitude using [trajectories.md](../../../docs/trajectories.md); the current Python recorder does not recreate the historical staged RS05 schedule merely by selecting its total duration. Keep `telemetry_hz=0` and inspect separately before or after recording. Select a feasible rate from observed transaction timing, especially for sequential SDO reads.

If a run fails or reports faults, retain its evidence, inspect the cause and resolve it before another enabled run. Use `motorfit off --setup "$SETUP"` when an explicit disable is needed; do not automatically repeat motion after a fault.

## Completion

Check `raw.json`, `samples.jsonl` and `frames.jsonl` for recording completion, faults, timestamps, sample count, actual duration and expected enable/disable behavior. Report unavailable feedback fields as unavailable. Preserve the motor/fixture/coordinate snapshot and encoded commands; configured voltage and nominal torque are not independent synchronous measurements. Keep failed runs separate from fit inputs and allocate whole runs to train, validation and final-test splits before identification.

## Maintenance sources

- [CLI](../../../src/motor_identification/cli.py) and [configuration loader](../../../src/motor_identification/config.py): flags and path/coordinate behavior.
- [MIT recorder](../../../src/motor_identification/acquisition/recorder.py) and [effort recorder](../../../src/motor_identification/acquisition/effort.py): timing, saved evidence and cleanup.
- [Protocol references](../../../docs/protocol-references.md): authoritative device-specific sources.

Recheck the matching driver and guide when adding a motor family or changing acquisition behavior.

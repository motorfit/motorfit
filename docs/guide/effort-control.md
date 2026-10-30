# Effort control

These native drivers connect the full **read → inspect → software zero → record → process → BAM fit → evaluate/plot** workflow. They have been tested with simulated CAN peers and the real BAM optimizer. Hardware commissioning remains necessary for each mounted device; the repository's measured reference motor is still RS05.

## Select a protocol and measure the setup

| Family | Setup template | Wire input | Setup details |
|---|---|---|---|
| MyActuator | [`myactuator_rmd_x_v3_pendulum.toml`](https://github.com/motorfit/motorfit/blob/main/configs/setups/myactuator_rmd_x_v3_pendulum.toml) | RMD-X V3 A1 current, 0.01 A/count | Set output-axis `torque_constant_nm_per_a` and `current_limit_a` in the motor profile; supplied 1.0 values are placeholders |
| HighTorque | [`hightorque_ht_can_pendulum.toml`](https://github.com/motorfit/motorfit/blob/main/configs/setups/hightorque_ht_can_pendulum.toml) | 05/13 pure torque, 0.01 Nm/count | Set the exact feedback CAN ID; default is 1 for motor 1. Some firmware uses standard ID `motor_id << 8` |
| Hexfellow 07 | [`hexfellow_canopen_v07_pendulum.toml`](https://github.com/motorfit/motorfit/blob/main/configs/setups/hexfellow_canopen_v07_pendulum.toml) | CANopen mode 4, 6071 permille of device peak torque | Firmware 07 uses Q21 revolutions and uint32 mNm peak torque |
| Hexfellow 08 | [`hexfellow_canopen_v08_pendulum.toml`](https://github.com/motorfit/motorfit/blob/main/configs/setups/hexfellow_canopen_v08_pendulum.toml) | CANopen mode 4, 6071 permille of device peak torque | Firmware 08 uses float32 revolutions and float32 Nm peak torque |

Copy the setup and motor profile for your actual motor; keep relative paths valid. The generic profile names are protocol identifiers, not hardware specifications. Configure the measured fixture, supply, physical angle/speed/torque limits and fixed host gains. Position limits in these profiles refer to the physical angle relative to the saved zero. Kp is Nm/rad and Kd is Nm·s/rad. Start from the 20 Hz low-amplitude acquisition template, then use measured transaction durations to choose a rate. SDO acquisition reads multiple registers sequentially and does not promise synchronized feedback or a 1 kHz loop.

MyActuator uses standard request ID `0x140 + motor_id` and reply ID `0x240 + motor_id`. This path targets the RMD-X V3 protocol, not older same-ID replies or newer incompatible protocol variants. Position comes from the signed multi-turn 92 reply; the ambiguous single-turn status field is not used. Feedback current is retained separately and converted with the same nominal output Nm/A scale. Current clipping and integer quantization are saved in the actual input.

HighTorque uses extended request ID `0x8000 | motor_id` and matches the exact configured reply ID. Its cooperative 07/35 mode limits torque and does not implement MIT Kp/Kd; MotorFit uses 05/13 instead. The basic feedback carries no enable, fault or temperature fields: these are marked unavailable, not inferred from a successful read. `watchdog_ms=0` is required because this adapter has no verified drive-watchdog configuration command. Configure and verify the drive's timeout externally; a host timeout/finally-stop cannot protect against host power loss or a broken bus.

Hexfellow opens SocketCAN with FD enabled. Configure the interface for the manufacturer's 1 Mbps arbitration / 5 Mbps data timing. SDO requests themselves are classic 8-byte frames on the FD-capable bus. The driver verifies 1018:03 against the selected firmware, reads 6076 for the torque scale and rejects incompatible experiment limits. It uses explicit, size-checked SDO replies, statusword checks and the torque-mode display. It configures consumer heartbeat 1016:01 in RAM, using master ID 126 (125 if the motor is 126); reserve that ID on this single-motor bench. Heartbeats come from the control loop, so a stalled loop stops refreshing them. It does not reset faults, remap PDOs, save parameters or change the short-circuit brake setting. Hexfellow's single-turn angle is wrapped around the saved downward coordinate; use this path for pendulum motion within one revolution.

MyActuator sets communication timeout B3 before enabling and verifies its echoed value. **B3 is stored by the device in ROM**, so recording changes that setting. Shutdown uses 80 and startup releases the brake with 77 before zero current. Neither these commands nor a software zero alter the encoder's hardware zero. Read/inspect/zero do not enable the new drivers.

## Record and identify

After selecting and editing a setup, use the same sequence for all three families. The example below selects HighTorque; substitute the appropriate setup above.

```bash
SETUP=configs/setups/hightorque_ht_can_pendulum.toml
uv run --frozen motorfit read --setup "$SETUP"
uv run --frozen motorfit inspect --setup "$SETUP" --out data/my-motor/inspection.json
# Place the pendulum at the known downward angle before saving this coordinate.
uv run --frozen motorfit zero --setup "$SETUP" --angle 0
uv run --frozen motorfit record --setup "$SETUP" --out data/my-motor/raw/train/run01 --kp 3
uv run --frozen motorfit record --setup "$SETUP" --out data/my-motor/raw/train/run02 --kp 4
uv run --frozen motorfit record --setup "$SETUP" --out data/my-motor/raw/validation/run01 --kp 5
uv run --frozen motorfit process --raw data/my-motor/raw/train \
  --out data/my-motor/processed/train --dt 0.05
uv run --frozen motorfit process --raw data/my-motor/raw/validation \
  --out data/my-motor/processed/validation --dt 0.05
uv run --frozen motorfit fit --logdir data/my-motor/processed/train --model m1 \
  --trials 1000 --output data/my-motor/candidates/m1.json
uv run --frozen motorfit fit --logdir data/my-motor/processed/validation \
  --eval --output data/my-motor/candidates/m1.json
uv run --frozen motorfit plot --logdir data/my-motor/processed/validation \
  --sim --params data/my-motor/candidates/m1.json
uv run --frozen motorfit off --setup "$SETUP"
```

Use an additional test directory of independent runs for the final `--eval`; the validation recordings above are for selecting the model, not for final test accuracy. Keep each mounted motor and fixture configuration in its own dataset. Review the [experiment workflow](../getting-started/workflow.md) before fitting long runs.

## Input timing and fitted meaning

The host reads state, calculates `Kp*(goal-q) - Kd*dq`, applies the configured torque/current bounds and sends the encoded effort. Each sample stores the returned state, sensor-read interval, command TX time, command-completion time, requested torque and actual encoded `control`. Original frames are flushed incrementally to `frames.jsonl`; samples go to `samples.jsonl`, and `raw.json` retains completion/failure and device information.

`process` linearly resamples sensor values but applies **zero-order hold at command TX times** to control and enable intent. It does not linearly interpolate discrete command steps or backdate the first nonzero input. Incomplete recordings and invalid timelines are rejected. The BAM adapter replays that input, including in vectorized train/validation batches; it never substitutes goal tracking error or measured load for the command. `command_delay` shifts the recorded effort sequence, and reset-period evaluation resets the simulated plant without rewinding the input.

The fitted parameters retain BAM's friction model, armature, angle offset, command delay and `torque_ratio`. For MyActuator, `profile torque_constant_nm_per_a * torque_ratio` is the fitted effective output Nm/A scale under the tested conditions; it is not an independent winding-constant measurement. For the other two, `torque_ratio` refines the nominal Nm command scale. Current-loop dynamics, voltage saturation and sensor calibration are not separately identified by this adapter.

BAM M1–M6 fitting, evaluation and `plot --sim` are supported. The separate MuJoCo/Newton/mjlab firmware-controller replay paths currently accept torque-MIT models only and reject these new families. See [protocol sources](../reference/protocols.md) and the [support matrix](../reference/motors.md).

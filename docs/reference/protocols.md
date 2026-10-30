# Protocol behavior

This page describes the implemented wire protocols and driver behavior. To choose
a motor profile, use [Motors](motors.md); to operate the bench, follow
[Record](../guide/acquisition.md).

## RobStride

The driver uses the manufacturer's private extended-CAN protocol. Position,
velocity, torque, Kp and Kd are quantized to 16-bit fields using the selected model's
ranges. A control request is followed by its addressed type-2 feedback response.

Startup stops the motor, prepares the supported operating mode and watchdog,
then enables control. Acquisition expects the reported mode to agree with the
requested enabled or disabled state. A fault, mode mismatch or missing reply
aborts the run and initiates cleanup.

The model TOMLs link to their manufacturer manuals. RS01/02/05/06 retain the pinned
manual references; RS00/03/04 retain their shipped ranges and gain limits pending
verification on the actual firmware and hardware.

Source: [RobStride product manuals at the referenced revision](https://github.com/RobStride/Product_Information/tree/667444b6d1f9fabe01b87765ee73abd29d54e71b).

## Damiao

The driver implements MIT mode over standard CAN. Position uses 16 bits; velocity,
torque, Kp and Kd use 12 bits. Kp is encoded over `[0, 500]` and Kd over `[0, 5]`.
Motor-specific position, velocity and torque ranges come from the profile.

Before enabling, the driver:

1. Stops the motor and reads PMAX, VMAX and TMAX.
2. Rejects a mismatch between those values and the profile.
3. Configures and verifies MIT mode and the TIMEOUT watchdog register.
4. Enables the motor and checks the reply status.

TIMEOUT is written as `round(watchdog_ms × 20)` ticks. This path does not issue a
firmware-zero, persistent-save or fault-clear command.

Replies must match both the configured feedback CAN ID and the motor nibble.
The original status is retained as `status_code`; recording normalizes `mode` to
0 for disabled and 2 for enabled. Motor and rotor temperatures are saved separately.

Source: [Damiao control examples at the referenced revision](https://github.com/dmBots/motor-control-routine/tree/ae6c1031056908d3d8059f003bd015a9d6b21894).

## Command and feedback evidence

Both drivers use serial request/reply transactions and drain queued frames before
sending a new request. Frames are saved even when they fail the reply filter.
There is no in-loop register-telemetry stream during recording.

Neither protocol supplies a transaction sequence number for this exchange.
Filtering reduces stale-response risk but cannot prove that an old delayed packet
will never arrive after a new request. The saved host timestamps indicate command
and reception times, not the motor's internal sampling clock.

Quantization can make the encoded value of a requested zero nonzero. MotorFit saves
encoded gains, velocity target and feedforward torque so the fitter reproduces the
actual command fields. Feedback `load` remains nominal firmware torque, without
independent shaft-torque calibration.

## Read and shutdown behavior

`inspect` reads registers without changing the enable state. It saves individual
read failures beside successful values. `read` and `zero` use a device context that
sends disable on exit. `record` attempts disable and bus closure after success,
errors or interruption; cleanup failures are retained in the recording.

These software behaviors are covered by protocol and failure-path tests. The
[RS05 study](../case-studies/rs05.md) provides the current recorded hardware evidence.

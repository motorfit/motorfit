# Recording

This guide covers the native RobStride and Damiao SocketCAN adapters. For MyActuator, HighTorque and Hexfellow, use the [recorded-effort workflow](effort-control.md), which includes their setup templates and different input timing. See [bring your own motor](configuration.md) for another model or controller family, and [the workflow](../getting-started/workflow.md) for experiment design.

Linux SocketCAN must already be configured for the actual interface and 1 Mbit/s bus. The supplied TOML files are templates. Set motor and feedback/host addresses, fixture, supply setting and a distinct coordinate file for the mounted device. `read` and `inspect` do not enable the motor. The pendulum-down convention is physical q=0 with encoder-positive direction.

```bash
uv run motorfit read --setup configs/setups/rs05_pendulum.toml
uv run motorfit inspect --setup configs/setups/rs05_pendulum.toml --out data/my-motor/inspection.json
```

After placing the mechanism at a known physical angle, `motorfit zero --setup ... --angle 0` stores a software offset. It does not move the device or set its firmware zero. An already calibrated mounted device keeps its existing zero when changing weights.

## Record and process

```bash
uv run motorfit record --setup configs/setups/rs05_pendulum.toml --out data/my-motor/raw/run01
uv run motorfit process --raw data/my-motor/raw/run01 --out data/my-motor/processed/train --dt 0.01
```

It saves raw CAN frames, per-transaction samples and BAM JSON. Driver errors, missing feedback and interruption trigger cleanup and preserve available evidence. Timing uses host feedback-reception timestamps, with the bus timestamp retained separately. Static supply/current inspection is not synchronous telemetry. The protocol has no transaction sequence number; local IDs are bookkeeping, not proof that a delayed reply is impossible. Duration comes from the acquisition configuration or `--duration`; see [trajectories](../reference/trajectories.md) for time scaling and experiment windows.

## Damiao

Use `configs/setups/dm4310_pendulum.toml` with the same `read`, `inspect`, `zero`, `record` and `process` commands. The profile, 12-bit gain encoding, runtime range checks and status conventions are described in [motor support](../reference/motors.md#damiao-acquisition). MyActuator, HighTorque and Hexfellow use the same CLI with the settings in the [recorded-effort guide](effort-control.md).

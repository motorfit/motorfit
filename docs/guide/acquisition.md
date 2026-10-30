# Record motion

This guide starts with `configs/local/bench.toml` from [Setup](configuration.md).
It covers one pilot recording, checking the result, and collecting the planned
training and evaluation runs.

`record` can enable the motor and move the arm. Confirm the assembly, clear travel
and physical stop/power control before running it. `inspect` reads registers;
`read` and `zero` do not enable motion and send a disable command when closing.

## 1. Bring up SocketCAN

MotorFit opens an existing Linux SocketCAN interface; it does not configure the
adapter or change motor addresses. For a bench configured for classic CAN at
1 Mbit/s, an example setup is:

```bash
sudo ip link set can0 down
sudo ip link set can0 up type can bitrate 1000000
ip -details -statistics link show can0
```

Replace the interface and bitrate if your hardware uses different settings. Check
that the reported bitrate matches the motor. `BUS-OFF` or rising bus-error counters
must be resolved before acquisition. The [Linux SocketCAN documentation](https://docs.kernel.org/networking/can.html#netlink-interface-to-set-get-devices-properties)
describes these interface settings.

Use one MotorFit process for the device at a time. Other command or telemetry
producers can interfere with request/reply matching.

## 2. Read feedback and inspect registers

```bash
uv run --no-sync motorfit read --setup configs/local/bench.toml
uv run --no-sync motorfit inspect --setup configs/local/bench.toml \
  --out data/my-motor/inspection-before.json
```

`read` prints the encoder position, velocity, nominal torque, status and temperature.
Its position is the **raw encoder coordinate**; the software zero is applied to
recorded positions later.

`inspect` saves register values and CAN frames in one JSON file. Look for per-register
`error` entries as well as values: a successful command can still report unsupported
or unanswered register reads. Use a new output filename for each inspection.

For Damiao, verify the profile's PMAX, VMAX and TMAX against the device. The driver
also checks those ranges before enabling. [Protocols](../reference/protocols.md)
describes the family-specific startup checks.

## 3. Save the downward zero

Place the pendulum at the downward position, then run:

```bash
uv run --no-sync motorfit zero --setup configs/local/bench.toml --angle 0
```

The command saves `zero_rad = encoder_position − physical_angle` in
`configs/local/bench-zero.toml`. It neither moves the arm nor changes the firmware
encoder zero. A different known physical angle can be supplied in radians.

Keep this coordinate for all runs on the same mounting. Changing only the tip
weight does not require a new zero; remounting or changing the encoder reference
does.

## 4. Record a pilot run

After choosing the gains, amplitude and duration in the motion file:

```bash
uv run --no-sync motorfit record --setup configs/local/bench.toml \
  --out data/my-motor/raw/pilot/run01
```

The command prints the model, trajectory, duration, gains and requested rate before
starting. It follows the target trajectory, saves feedback, and attempts to disable
the motor at the end. `Ctrl+C` interrupts acquisition and also attempts cleanup.
A new run must use a new directory.

Three files appear:

| File | Contents |
|---|---|
| `raw.json` | Configuration snapshot, samples, completion flag and any errors |
| `samples.jsonl` | Samples flushed incrementally, one JSON object per line |
| `frames.jsonl` | Sent and received CAN frames, including discarded frames |

The driver stops on missing replies, reported faults or an unexpected enable state.
Available evidence is retained even when a run fails. A failed disable attempt is
recorded as `cleanup_error`.

## 5. Check the recording

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
log = json.loads(Path("data/my-motor/raw/pilot/run01/raw.json").read_text())
times = [row["timestamp"] for row in log["entries"]]
gaps = [b - a for a, b in zip(times, times[1:])]
print("Completed:", log["completed"], "Samples:", len(times))
print("Errors:", log.get("error"), log.get("cleanup_error"))
print("Largest feedback interval [s]:", max(gaps, default=None))
print("Fault samples:", sum(bool(row["faults"]) for row in log["entries"]))
PY
```

Require a completed run with no acquisition or cleanup error before admitting it
to a fitting split. Compare feedback intervals with the requested period (`1/hz`)
and examine any long gaps. At 100 Hz the requested period is 10 ms; the actual
host loop is not a hard real-time clock.

For a graphical timing check:

```bash
uv run --no-sync motorfit jitter --logdir data/my-motor/raw/pilot
```

This opens a histogram of raw sample intervals. Review the position trace too:
unexpected oscillation, clipping or a coordinate discontinuity needs investigation
before collecting more runs. `process` resamples the input; it does **not** decide
whether a failed or poor-quality experiment is suitable for fitting.

## 6. Collect the planned runs

Use the split directories from [Workflow](../getting-started/workflow.md). For example,
after commissioning the setup:

```bash
uv run --no-sync motorfit record --setup configs/local/bench.toml \
  --trajectory sin_time_square --out data/my-motor/raw/train/sweep-r01
uv run --no-sync motorfit record --setup configs/local/bench.toml \
  --trajectory sin_sin --out data/my-motor/raw/validation/mixed-r01
```

These illustrate naming and command overrides; they are not a complete experiment.
Follow your planned repetitions, loads and gains. Update the fixture file when
changing a weight, and keep training durations consistent. Each recording saves
the resolved settings, including command-line overrides.

Move failed runs into `data/my-motor/raw/failed/`. To explicitly disable an idle
bench from the command line, use `motorfit off --setup configs/local/bench.toml`.

When the required runs have passed review, continue with [Fit a model](identification.md).

## If acquisition fails

| Symptom | Check |
|---|---|
| No matching feedback | Power, wiring, bitrate, motor address and reply/host address |
| Damiao range mismatch | Selected model profile and device PMAX/VMAX/TMAX; do not change limits merely to suppress the check |
| Missing `zero_rad` | Run `zero` at a known physical angle |
| Existing output files | Choose a new run directory |
| Long feedback gaps | Host load, bus traffic, requested rate and reply timeouts |
| Fault or unexpected mode | Saved status/frame evidence and the manufacturer's fault definition |

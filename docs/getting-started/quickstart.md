# Quickstart

Record motion from a motor, fit an actuator model, and check its predictions on a
second recording. You will finish with a `model.json` fitted to your own data.

You need a [supported motor](../reference/motors.md), a pendulum fixture with
measured properties, and a Linux machine with a SocketCAN adapter.

## 1. Install MotorFit

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and use
**Python 3.12**. Cloning requires access to the source repository and a GitHub SSH
key. Run the remaining commands from the repository root.

```bash
git clone --recurse-submodules git@github.com:motorfit/motorfit.git
cd motorfit
uv sync --frozen
```

## 2. Configure the bench

Follow [Set up the bench](../guide/configuration.md) to create
`configs/local/bench.toml` with your motor profile, measured fixture and motion
settings. [Bring up SocketCAN](../guide/acquisition.md#1-bring-up-socketcan) at the
bitrate configured on your motor. Check that feedback arrives, then place the
pendulum at its downward position and save the zero.

```bash
uv run --no-sync motorfit read --setup configs/local/bench.toml
uv run --no-sync motorfit zero --setup configs/local/bench.toml --angle 0
```

## 3. Record two runs

`record` enables the motor and moves the arm. Confirm the mounting, clear travel,
and access to a physical stop or power cutoff before starting. Use a motion and
gains suited to the actual setup.

```bash
uv run --no-sync motorfit record --setup configs/local/bench.toml \
  --out data/first-fit/raw/train/run01
uv run --no-sync motorfit record --setup configs/local/bench.toml \
  --out data/first-fit/raw/check/run02
```

Use the first run for fitting and keep the second for checking predictions.
[Check each recording](../guide/acquisition.md#5-check-the-recording) for
completion, feedback gaps and errors before processing it.

## 4. Fit and check the model

Resample each run to a uniform time grid. The example uses `0.01` seconds for a
capture with feedback near 100 Hz.

```bash
uv run --no-sync motorfit process \
  --raw data/first-fit/raw/train --out data/first-fit/processed/train --dt 0.01
uv run --no-sync motorfit process \
  --raw data/first-fit/raw/check --out data/first-fit/processed/check --dt 0.01

uv run --no-sync motorfit fit \
  --logdir data/first-fit/processed/train --model m1 --trials 100 \
  --output data/first-fit/model.json
uv run --no-sync motorfit fit \
  --logdir data/first-fit/processed/check --eval \
  --output data/first-fit/model.json
```

The first `fit` writes `data/first-fit/model.json`. The second loads that file and
prints the mean absolute angle error in radians on the separate recording.
This small fit checks the end-to-end workflow. To build a model for use in
simulation, [plan an experiment](workflow.md) with multiple motions and loads,
then [evaluate the selected model](../guide/validation.md) on held-out runs.

(run-the-offline-example)=

For the bundled recordings, replay commands and published errors, see
[the RS05 case study](../case-studies/rs05.md#reproduce-three-recorded-runs).

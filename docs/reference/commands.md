# Command reference

Run commands from the repository root after `uv sync --frozen`. The examples use
`uv run --no-sync motorfit` to keep the installed environment unchanged.

## Main commands

| Command | Input | Result / device effect |
|---|---|---|
| `motors` | Optional `--json` | Lists profiles and validation coverage |
| `read --setup FILE` | Bench setup | Reads raw feedback; disables on exit |
| `inspect --setup FILE --out FILE` | Bench setup | Saves register reads and frames; does not enable or disable |
| `zero --setup FILE --angle RAD` | Known physical angle | Saves software zero; disables on exit |
| `off --setup FILE` | Bench setup | Sends disable |
| `record --setup FILE --out DIR` | Configured bench | Executes one trajectory and saves the capture |
| `process --raw PATH --out DIR --dt SEC` | One raw JSON or a tree of runs | Writes uniform-grid JSON logs |
| `jitter --logdir PATH` | Raw JSON or a tree of runs | Opens a sample-interval histogram |
| `fit --logdir DIR …` | Flat directory of processed logs | Fits or evaluates a model |
| `plot --logdir DIR --sim --params FILE …` | Processed logs and models | Opens BAM comparison plots |
| `verify --dataset FILE` | Portable dataset manifest | Checks input integrity |
| `demo --dataset FILE --output DIR` | Manifest and saved BAM references | Reproduces references and writes plots/metrics |
| `replay --dataset FILE --engine NAME --output DIR` | Manifest with an M1 model | Writes physics predictions and metrics |

For acquisition details, follow [Record](../guide/acquisition.md). For the
meaning of each input, see [Data formats](data.md).

## Recording overrides

These options replace the corresponding motion-file value for one run:

| Option | Unit / meaning |
|---|---|
| `--trajectory` | [Trajectory name](trajectories.md) |
| `--duration` | Seconds; overrides `duration_s` |
| `--amplitude` | Angle multiplier |
| `--kp`, `--kd` | Fixed position and velocity gains |
| `--hz` | Requested command rate |
| `--sweep-k` | Coefficient for `soccer_sweep` |
| `--telemetry-hz` | Must be zero; inspection is a separate operation |

If `--out` is omitted, recording creates a timestamped directory under
`data/raw/<motor-name>/`. Explicit paths make study organization clearer.

## Fitting options

```bash
uv run --no-sync motorfit fit \
  --logdir data/my-motor/processed/train --model m1 --trials 1000 \
  --output data/my-motor/candidates/m1-run01.json
```

| Option | Behavior |
|---|---|
| `--model` | `m1` through `m6`; required for a new fit |
| `--trials` | Optimizer budget; default is 100,000 |
| `--method` | `cmaes` (default), `random` or `nsgaii` |
| `--output` | New JSON to write; with `--eval`, existing model to read |
| `--eval` | Full-log evaluation without optimization |
| `--reset_period` | Optional periodic reset to measured state, in seconds |
| `--set` | Dictionary of independently chosen parameter values to hold fixed |
| `--validation_kp` | Optional internal holdout of logs with this requested Kp; default 0 disables it |
| `--wandb` | Enables the upstream Weights & Biases integration |

For example, if an independent measurement establishes an added inertia of
`0.0002 kg·m²`, append `--set '{"armature": 0.0002}'` to the fit command.
The dictionary is evaluated by the pinned BAM CLI; use only values you intentionally
provide. The numerical value here is a syntax example, not a motor estimate.

MotorFit infers `--actuator` from the saved motor snapshot. BAM's help text still
marks it as required because the underlying parser is shared. `--model` is also
unnecessary for MotorFit's `--eval` path, which reads the family from the model.

`--load-study` appears in upstream help but is not implemented in the pinned BAM
revision; MotorFit rejects it. The main guides use one worker and separate split
directories. Advanced worker and W&B options are inherited from BAM.

## Plotting and physics replay

Use `plot --sim` for BAM overlays. The inherited `--sim-mujoco` and `--sim-mjlab`
options target BAM's own simulator integrations; they are not the MotorFit
pendulum replay workflow. Use `motorfit replay` with its supported
[backend](backends.md) instead.

`replay --dt` sets the physics timestep (default `0.002 s`). CAD fixtures,
solver-option fragments and release-event studies are described with the
[RS05 example](../case-studies/rs05.md#advanced-validation), where their required
inputs are available.

## RS05 archive tools

`export-formal` converts the historical CSV/wire format to BAM JSON.
`audit-feedback` compares original capture evidence, and `release-replay` evaluates
alternative disable-event times. These commands expect the RS05 archive's capture
conventions; they are not prerequisites for a new native recording.

Run `uv run --no-sync motorfit COMMAND --help` for the parser's complete option list.

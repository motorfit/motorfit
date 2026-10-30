# Evaluate the model

Evaluate the selected model on complete recordings that were not used to fit its
parameters or choose its family. Keep the model fixed throughout this evaluation.
The commands on this page run offline.

## 1. Evaluate final-test recordings

```bash
uv run --no-sync motorfit process \
  --raw data/my-motor/raw/test --out data/my-motor/processed/test --dt 0.01
uv run --no-sync motorfit fit \
  --logdir data/my-motor/processed/test --eval \
  --output data/my-motor/selected/model.json
uv run --no-sync motorfit plot \
  --logdir data/my-motor/processed/test --sim \
  --params data/my-motor/selected/model.json
```

Use the same processing timestep and evaluation convention as in model selection.
Without `--reset_period`, each simulation starts from the recording's initial
position and speed, then runs without resetting to measurements. A periodic reset
changes the question being tested and must be reported if used.

The aggregate score averages each log's position MAE equally. It can hide a bad
release or a single poorly predicted load. Inspect the plots and evaluate important
conditions separately; a directory containing only one processed log gives that
log's score with the same command.

## 2. Diagnose the remaining error

| Pattern in the residual | What to investigate |
|---|---|
| Nearly constant position bias | Software zero, fixture geometry and fitted `q_offset` |
| Phase mismatch that grows with motion speed | Command delay, sample timing and the controller law |
| Error around reversals or near rest | Friction model and low-speed data coverage |
| Error changes strongly with load | Tip mass, radius, fixture inertia and torque scaling |
| Error concentrated at torque release | Enable timing and passive mechanics |

These are diagnostic starting points, not unique explanations. Test a proposed
cause against additional evidence. The [RS05 results](../case-studies/rs05-findings.md)
show a case where correcting event timing improved the early trajectory but did
not explain the final stopping error.

## Replay in a physics backend

The included replay adapters support **M1, torque-MIT control and the pendulum
fixture**. They compare a fixed model in another engine with both measurements and
saved BAM predictions.

For a complete runnable example:

```bash
uv sync --frozen --extra simulation
uv run --no-sync motorfit replay \
  --dataset tests/fixtures/offline/manifest.json \
  --engine mujoco --dt 0.002 --output outputs/mujoco-evaluation
```

`--dt` here is the **physics timestep**, not the processed sample interval. It must
divide the recording timestep; for logs at `0.01 s`, `0.002 s` gives five physics
steps per sample. Replay preserves the recorded controller gains, commands,
enable flags and initial state.

| Output | Purpose |
|---|---|
| `metrics.csv` | Errors for each recording |
| `metrics.json` | Per-record values and averages by split |
| `predictions/` | Saved simulated states, commands and measured values |
| `scenes/` | The generated pendulum MJCF scenes |
| `protocol.json` | Model hash, engine versions, timestep and solver settings |
| `COMPLETE.json` | Completion and unchanged-input checks |

Read `position_mae_rad` as simulator-versus-measurement error.
`delta_bam_position_mae_rad` is simulator-versus-BAM disagreement. Agreement between
two simulators checks implementation consistency; it does not remove an error
shared by both models.

The replay manifest format requires curated recordings and saved reference
predictions. A new `record` directory is not yet such a dataset. Use the ordinary
`fit --eval`/`plot --sim` path above for a new study, or prepare the
[dataset format](../reference/data.md#portable-datasets) for packaged replay.

[Backends](../reference/backends.md) covers Newton and mjlab runtimes. M2–M6 can be
evaluated with BAM; the current MotorFit physics adapters do not implement them.

## 3. Report the result

Keep the following with the selected model:

- Motor identity, mounting, loads, supply and controller gains.
- Training, validation and test run lists.
- Model file, input hashes and software revision.
- Per-condition errors, the worst runs and representative residual plots.
- Any simulator version, timestep, solver options and reset convention used.

Use the acceptance criteria chosen for your application. The replay tool's
`trajectory_gate_pass` records an inherited 5 mrad mean-error check per split;
it is not a universal accuracy requirement or proof of satisfactory release
behavior.

An actuator model is ready for integration when its errors are understood and
acceptable over the intended conditions. [Parameters](../reference/parameters.md#using-the-model-in-simulation)
explains what carries into a robot simulation and what still requires controller
or coordinate handling.

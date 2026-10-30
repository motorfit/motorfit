# Validation

Evaluate a fixed model on recordings that were not used to choose its parameters.
Check agreement with measurements first, then compare supported physics backends.
The [workflow](../getting-started/workflow.md) explains how to separate these decisions.
All commands on this page run offline.

## Check the dataset

A dataset manifest names the model, recordings, split labels and reference
predictions using relative paths and SHA-256 hashes. For the bundled sample:

```bash
uv run --frozen motorfit verify --dataset tests/fixtures/offline/manifest.json
uv run --frozen motorfit demo \
  --dataset tests/fixtures/offline/manifest.json --output outputs/validation-demo
```

`verify` detects missing or modified inputs. `demo` reruns the frozen BAM model,
compares its predictions with the saved reference and plots error against measured
motion. Matching a saved prediction checks reproducibility; measured residuals
show the model's remaining error. Use a new output directory for each run.

For your own study, supply its manifest under `data/<study>/`. The CLI reads a
prepared manifest; it does not infer the split or build a new study automatically.

## Evaluate held-out recordings

If you have processed recordings but no manifest, evaluate the fixed parameter
file directly with BAM:

```bash
uv run --frozen motorfit fit \
  --logdir data/my-motor/processed/test --eval \
  --output data/my-motor/candidates/m1.json
```

The `--eval` flag loads the model without fitting. Select it on validation data
before using the final test directory. Report operating conditions and errors
by recording or split, rather than using an average to hide a failing condition.

## Replay in a physics backend

The included adapters implement **M1, torque-MIT control and the pendulum rig**.
BAM fitting also supports M2–M6, but these do not yet
have corresponding MuJoCo/Newton/mjlab replay adapters.

```bash
uv sync --frozen --extra simulation
uv run --frozen --extra simulation motorfit replay \
  --dataset tests/fixtures/offline/manifest.json --engine mujoco \
  --dt 0.002 --output outputs/mujoco
```

Replay uses the same initial state, encoded commands, enable flags and frozen
parameters as the saved recording. Without `--scene-assets`, it uses the
identification-equivalent point-load fixture. A new manifest does not implement
a different controller or fixture equation.

Use `--engine newton` or `--engine mjlab` from a compatible independent environment;
see [Backends](../reference/backends.md). Requested options are checked against the
selected backend. Keep solver settings, timestep, delay, friction and disable
handling in the comparison report alongside position error.

## Inspect and report results

Keep the model hash, dataset split, software versions, solver options and timestep
with the generated metrics and trajectories. Compare BAM-to-measurement error
separately from simulator-to-BAM disagreement. Simulator agreement does not establish
that a model explains unmeasured hardware behavior.

The [RS05 study](../case-studies/rs05.md#advanced-validation) adds independent CAN
audits, CAD scenes, release-event timing and video rendering. Those tools depend
on its archived evidence and capture conventions. Software regression coverage is
described in [Contributing](../development/contributing.md#development-environment).

---
name: motorfit-validate
description: Evaluate a fixed MotorFit model against recorded motion and, when supported, replay it in MuJoCo, Newton or mjlab. Use for held-out evaluation, dataset integrity checks or simulator comparison without refitting parameters.
---

# Validate a fixed model

Run commands from the MotorFit repository root. Read [validation.md](../../docs/validation.md) and the relevant backend section of [environments.md](../../docs/environments.md). Establish the model, evaluation recordings, intended comparison and output location before running.

## Choose the validation path

- **Processed logs and a fitted model:** use BAM evaluation below. Motor snapshots must match. This supports M1–M6 and both torque-MIT and recorded-effort inputs.
- **A dataset manifest with saved references:** first run `motorfit verify --dataset <manifest>`. Resolve its paths relative to the manifest and check hashes and split counts. The manifest must reference the intended fixed model; do not rewrite hashes to conceal a mismatch.
- **Bundled offline example:** `motorfit demo` verifies the manifest, reproduces saved BAM predictions and writes a headless comparison. For a new study, a manifest indexes prepared data and predictions; no CLI automatically creates a complete study or reference predictions.
- **Physics replay:** the current adapters support M1, torque-MIT control and the implemented pendulum dynamics. Check the model snapshot and rig before selecting a backend. M2–M6, recorded-effort models and other rigs require additional physics integration. Complete applicable BAM checks and state the unsupported part; do not silently substitute M1 or a different controller.

For an existing processed evaluation split, set paths to the user's fixed artifacts:

```bash
uv run --frozen motorfit fit --logdir outputs/my-motor/processed/test \
  --eval --output outputs/my-motor/frozen.json
```

Here `--output` names the model to read, and `--eval` prevents fitting. Preserve the model hash before and after evaluation. Capture the printed score: mean per-record position MAE in radians. Use `motorfit plot --logdir <processed-split> --sim --params <model.json>` for trajectory inspection when needed. Declare state-reset settings and evaluate the final split only after model selection is fixed.

## Replay a supported model

For the bundled example with MuJoCo, use a new output directory:

```bash
uv run --frozen motorfit verify --dataset examples/offline/manifest.json
uv sync --frozen --extra simulation
uv run --frozen --extra simulation motorfit replay \
  --dataset examples/offline/manifest.json --engine mujoco \
  --dt 0.002 --output outputs/validation-mujoco
```

Replace the manifest for a compatible prepared study. Choose a positive physics timestep that divides the processed recording interval. Run Newton or mjlab from their separately managed environment as described in the environment guide; do not merge historical dependency overrides into the core lock. Keep recorded initial conditions, commands, model parameters and torque-disable events fixed when comparing engines.

Without `--scene-assets`, replay uses the identification-equivalent point-load fixture. The supplied CAD assets describe the RS05 bench; use them only for that assembly. `--fixture-model identified_point` retains its CAD appearance with identification-equivalent inertia. Changes to timestep, solver, friction or fixture assumptions define a new comparison and should be reported. Use `--ablations` only when requested or needed to diagnose differences; those runs use training data.

The feedback audit and release-event commands use the RS05 reference capture conventions. Follow [validation.md](../../docs/validation.md) for those investigations; their decoding and timing assumptions do not automatically apply to another motor or wire format.

## Completion

Inspect replay `metrics.json`, `metrics.csv`, saved trajectories and protocol metadata. Report error against measurements separately from disagreement with BAM or saved references, with split counts, worst runs, model hash and engine/version/timestep settings. Agreement between simulators does not establish physical accuracy. Apply the user's declared tolerance; repository benchmark gates are not universal acceptance criteria. Keep fixed inputs unchanged and distinguish executed checks from unsupported or unavailable checks.

## Maintenance sources

- [Dataset loader](../../src/motor_identification/dataset.py) and [verification](../../src/motor_identification/validation/verify.py): manifests and integrity checks.
- [Replay entry point](../../src/motor_identification/identification/validate_simulation.py), [M1 adapter](../../src/motor_identification/identification/mujoco.py) and [BAM runner](../../src/motor_identification/identification/bam/runner.py): supported models, metrics and runtime options.

Recheck these sources when model support, backend behavior or result schemas change.

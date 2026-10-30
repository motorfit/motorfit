---
name: motorfit-identify
description: Process recorded motor data, fit BAM M1–M6 candidates and select a MotorFit model on independent recordings. Use for parameter identification or model selection; use motorfit-validate to evaluate an already fixed model.
---

# Identify motor dynamics

Run commands from the MotorFit repository root. Read [the workflow](../../../docs/getting-started/workflow.md) and [BAM identification](../../../docs/guide/identification.md). For MyActuator, HighTorque or Hexfellow, also read the input-timing section of [Effort control](../../../docs/guide/effort-control.md).

## Establish the dataset

1. Locate complete raw recordings or already processed BAM logs. Check motor identity and snapshot, controller mode, coordinates, fixture measurements, command units and timing. Preserve raw data and exclude incomplete or faulty runs with a recorded reason.
2. Declare training, model-selection validation and final-test sets by whole recordings before fitting. Keep repeated or overlapping samples from a run together; do not claim independent test accuracy from training inputs. The CLI does not assign these splits automatically.
3. Keep each processed split in its own directory, with only its BAM log JSON files at the top level. One fit requires consistent motor snapshots and a shared resampling interval. Select `dt` from recorded timing and required bandwidth, not from a desire to create more samples.

For a new study, replace the example paths below with the declared split directories and use new output locations. Process the other splits separately with the same `dt`; skip processing when suitable processed inputs already exist.

```bash
uv run --frozen motorfit process \
  --raw outputs/my-motor/raw/train --out outputs/my-motor/processed/train --dt 0.01
```

`process` selects recorded-effort handling from the log. It holds encoded effort at command TX times while interpolating sensors. Do not replace commands with measured load or reconstruct them from tracking error. Torque-MIT logs instead replay the recorded controller law and quantized fields.

## Fit and select

Start with M1 or the user's chosen family and a declared trial budget. BAM supports M1–M6; select among requested candidates using the validation recordings, with repeated optimization runs when warranted. Create the output parent first and choose a new `.json` filename for every fit: fitting can overwrite an existing file immediately.

```bash
mkdir -p outputs/my-motor/candidates
uv run --frozen motorfit fit --logdir outputs/my-motor/processed/train \
  --model m1 --trials 1000 --output outputs/my-motor/candidates/m1-run01.json
uv run --frozen motorfit fit --logdir outputs/my-motor/processed/validation \
  --eval --output outputs/my-motor/candidates/m1-run01.json
```

The trial count is an example budget, not an accuracy guarantee. Save the commands, options, data hashes, split lists, scores and selection rule. Check `motorfit fit --help` before using extra flags: the pinned implementation has no `--seed` option and rejects `--load-study`; do not promise seeded reproducibility or resumable optimization through those flags. Leave external experiment uploads disabled unless requested.

Use `motorfit plot --logdir <processed-split> --sim --params <candidate.json>` for BAM trajectory inspection when useful. `fit --eval` prints the mean per-record position MAE in radians; preserve that result rather than treating the candidate's stored training metric as validation accuracy. Report any periodic state-reset setting; omitting `--reset_period` evaluates uninterrupted trajectories.

## Freeze the result

Freeze the selected parameter file and its complete `motor_spec`, dataset hashes, controller/fixture definitions and selection evidence before evaluating the final split with `fit --eval`. Load saved models through `motorfit.identification.bam.load_model(path)` so current TOML edits cannot reinterpret them. Never direct a new fit at a frozen model, including `tests/fixtures/offline/model.json`.

Report the candidate comparison, selected model path, held-out score and limitations of the tested conditions. The three bundled example recordings and a short fit demonstrate the API; they do not repeat formal RS05 model selection. Physical replay support is narrower than BAM fitting support; use [motorfit-validate](../motorfit-validate/SKILL.md) for a fixed model.

## Maintenance sources

- [BAM runner](../../../src/motorfit/identification/bam/runner.py), [fitting](../../../src/motorfit/identification/bam/fitting.py) and [resampling](../../../src/motorfit/identification/bam/resample.py): snapshot checks, scoring and input timing.
- [Pinned BAM CLI](../../../third_party/bam/bam/fit.py): optimization flags and model selection.

Recheck these sources when fitting flags, supported controllers or snapshot formats change.

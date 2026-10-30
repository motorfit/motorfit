# Fit a model

Start with reviewed recordings arranged under `data/my-motor/raw/train/` and
`data/my-motor/raw/validation/`. This guide resamples them, fits an M1 candidate,
and evaluates it before choosing a final model. No hardware is used.

## 1. Process each split

```bash
uv run --no-sync motorfit process \
  --raw data/my-motor/raw/train --out data/my-motor/processed/train --dt 0.01
uv run --no-sync motorfit process \
  --raw data/my-motor/raw/validation --out data/my-motor/processed/validation --dt 0.01
```

`--dt` is the processed sample interval in seconds; `0.01` gives 100 Hz. Choose it
from the measured timing and motion bandwidth. A smaller interval interpolates
more points but does not create new measurements.

`process` finds nested `raw.json` files and writes a flat directory of processed
JSON logs. It retains the recording metadata and linearly interpolates numeric
sample fields. The torque-enable field is interpolated and thresholded at 0.5;
its transition time is therefore approximate. Keep the raw capture for precise
release-event analysis.

Use a new or empty processed directory when changing the run selection or timestep:
old files are not removed automatically. Keep inspection JSON and summaries out of
these directories; `fit` treats every top-level `.json` as a recording.

## 2. Check the training inputs

All logs in a fit must have the same complete `motor_spec` and the same `dt`.
Loads and controller gains can differ and are read from each recording.

**The batch fitter uses only as many samples as the shortest training log.**
Keep training durations consistent or deliberately prepare matched windows.
A long recording mixed with short recordings does not contribute its extra tail
to the fit. Later `--eval` runs evaluate the full individual logs.

## 3. Fit the first candidate

```bash
mkdir -p data/my-motor/candidates data/my-motor/selected data/my-motor/results
uv run --no-sync motorfit fit \
  --logdir data/my-motor/processed/train --model m1 --trials 1000 \
  --output data/my-motor/candidates/m1-run01.json
```

The optimizer minimizes position mean absolute error. It periodically saves the
best candidate and prints its score in radians. The final JSON includes:

- The model family and fitted parameters.
- The complete motor specification copied from the recordings.
- `identification.training_mae_rad`, the best training score.

The parent output directory must already exist. Use a fresh filename: fitting
opens the specified file for writing. If interrupted after a completed trial,
MotorFit saves the best completed candidate.

A budget of 1,000 trials is a starting example, not a convergence guarantee. Repeat
fits and check whether validation error and parameters are stable. The current CLI
does not expose an optimizer-seed option; save the source revision, input selection,
arguments and each output when comparing runs.

## Evaluate and inspect

```bash
uv run --no-sync motorfit fit \
  --logdir data/my-motor/processed/validation --eval \
  --output data/my-motor/candidates/m1-run01.json
uv run --no-sync motorfit plot \
  --logdir data/my-motor/processed/validation --sim \
  --params data/my-motor/candidates/m1-run01.json
```

With `--eval`, `--output` names the existing model to **read**. No fitting occurs.
The printed `Score` is the mean of the position MAEs calculated separately for
each complete log; every log has equal weight. `plot --sim` opens Matplotlib plots
with BAM predictions overlaid on the measurements.

Inspect reversals, fast motion, release and final settling. Two models with similar
average error can behave very differently in those windows.

## Compare model families

[Parameters](../reference/parameters.md#model-families) describes M1–M6. To test an
additional friction model, repeat the fit with a different `--model` and output
filename, then evaluate it on the **same** validation recordings. For example:

```bash
uv run --no-sync motorfit fit \
  --logdir data/my-motor/processed/train --model m2 --trials 1000 \
  --output data/my-motor/candidates/m2-run01.json
uv run --no-sync motorfit plot \
  --logdir data/my-motor/processed/validation --sim \
  --params data/my-motor/candidates/m1-run01.json data/my-motor/candidates/m2-run01.json
```

Prefer the simpler model when the additional terms do not improve the validation
behaviors that matter. A parameter repeatedly reaching its search bound calls for
checking units, fixture properties and data coverage before changing that bound.

If a parameter has been measured independently, `--set` can hold it fixed. The
[command reference](../reference/commands.md#fitting-options) gives the syntax.

## Save the selected model

After comparing candidates, copy the chosen file to a stable study location:

```bash
cp data/my-motor/candidates/m1-run01.json data/my-motor/selected/model.json
```

Use the actual chosen candidate if it differs. Record the selection reason and
validation scores beside it. Continue with [Evaluate the model](validation.md)
using the final-test recordings.

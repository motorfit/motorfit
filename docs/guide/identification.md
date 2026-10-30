# Identification

MotorFit uses the pinned, unchanged [Rhoban BAM](https://github.com/Rhoban/bam)
submodule for M1–M6 actuator models, resampling, simulation and optimization.
Local adapters supply the controller law, recorded inputs and measured fixture.

Before fitting, finish the [experiment plan](../getting-started/workflow.md),
check recording completion and keep training, validation and final-test runs separate.

## Process recordings

Process each split independently. Choose `dt` from the recorded timing and the
bandwidth needed for the study:

```bash
uv run --frozen motorfit process \
  --raw data/my-motor/raw/train --out data/my-motor/processed/train --dt 0.01
uv run --frozen motorfit process \
  --raw data/my-motor/raw/validation --out data/my-motor/processed/validation --dt 0.01
```

Keep original raw data alongside the processed inputs. Recordings in one fit must
carry a consistent motor snapshot. For current/torque-command drivers, review
[effort control](effort-control.md#input-timing-and-fitted-meaning): their discrete
control inputs use zero-order hold at actual command transmission times.

## Fit a candidate

```bash
uv run --frozen motorfit fit \
  --logdir data/my-motor/processed/train --model m1 --trials 1000 \
  --output data/my-motor/candidates/m1.json
```

This fits only the supplied directory. The trial count is an example budget;
compare candidate families and repeated runs on the declared validation data.
Record seeds, options and the selection rule. `motorfit fit --help` lists the
supported fitting flags. Choose a new output path rather than overwriting a
selected model or the bundled fixture.

## Evaluate and inspect

```bash
uv run --frozen motorfit fit \
  --logdir data/my-motor/processed/validation --eval \
  --output data/my-motor/candidates/m1.json
uv run --frozen motorfit plot \
  --logdir data/my-motor/processed/validation --sim \
  --params data/my-motor/candidates/m1.json
```

Evaluation loads the fixed candidate. Inspect residuals across trajectories,
loads and gains before selecting it. Freeze the selected parameter file and input
hashes, then evaluate independent final-test recordings using [Validation](validation.md).

## Interpret the model

For torque-MIT recordings, the nominal command law is:

```text
Kp * (delayed_goal - q) + Kd * (goal_speed - dq) + feedforward
```

The nominal output is clamped to the protocol torque range; `torque_ratio` maps it
to effective torque. Recorded quantized gains and encoded velocity/feedforward
zeros are retained. Only the position goal receives the identified fractional
delay; disabling torque is a separate event.

Recorded-effort adapters instead replay the saved current/torque command. Neither
path independently identifies winding resistance, electrical torque constant,
current-loop dynamics or the calibration of a torque sensor.

Parameter JSON includes a complete motor snapshot. Python callers should use
`motorfit.identification.bam.load_model(path)` so a later TOML edit cannot reinterpret
a saved model. The [RS05 study](../case-studies/rs05.md) documents one completed
selection and its limitations; its three-record fixture is an installation sample,
not enough data to reproduce the full model-selection study.

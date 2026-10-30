# Plan an identification experiment

A useful model must predict motion beyond the recordings used to fit it. Plan the
loads, trajectories and evaluation conditions before collecting data, then keep
those choices with the results.

This workflow identifies one mounted motor at a time. A new unit, changed gearbox
or substantially different operating range needs its own measurements.

## Decide what the model must reproduce

Write down the expected range of joint angle, speed, load and controller gains.
Choose an error measure relevant to the task: tracking MAE, peak error, settling
position or release behavior. Use that same definition when comparing candidates.

Start with M1, which estimates torque scaling, added inertia, command delay,
coordinate offset and Coulomb/viscous friction. [Parameters](../reference/parameters.md)
explains these terms and the extra friction terms in M2–M6.

## Choose motions and loads

The experiment needs more than one kind of motion:

| Motion or change | What it helps reveal |
|---|---|
| Slow motion and reversals | Friction near zero speed and residual position bias |
| A frequency sweep | Tracking over different speeds and accelerations |
| A different known load | Whether torque scaling and inertia explain changed dynamics |
| Different gains | Whether the fitted model generalizes beyond one controller setting |
| Lift and release | Passive motion and stopping after torque is disabled |

Use [the trajectory reference](../reference/trajectories.md) to choose actual
command names and understand amplitude and time scaling. Measure fixture masses
and inertia separately: a wrong fixture model can be absorbed into fitted motor
parameters.

## Separate the recordings

Assign complete runs to three groups:

- **Training:** the optimizer uses these to choose parameters.
- **Validation:** use these to choose model family, trial budget and other fitting choices.
- **Final test:** evaluate the selected model after those choices are fixed.

Hold out conditions that matter to the intended use, such as an unseen load or
gain. Keep repeated samples from the same recording together. Repeated runs also
show whether differences between models exceed ordinary experiment variation.

Use the same planned duration for training runs: the current BAM batch fitter
truncates every training log to the shortest one. All training logs must also use
the same processed timestep. Evaluation can use each complete recording.

## Keep the study in one place

```bash
mkdir -p data/my-motor/raw/{pilot,train,validation,test,failed}
mkdir -p data/my-motor/{processed,candidates,selected,results}
```

Use descriptive run directories, for example
`raw/train/100g-sweep-r01/`. Each contains a complete capture and its configuration
snapshot. Keep a run list with the motor identity, load, gains, trajectory, repeat
and assigned split. The directory arrangement does not automatically add split
labels to the JSON files.

Pilot runs establish working settings. Move failed runs outside directories sent
to `process`; keep their evidence for diagnosis. The data-format reference explains
[which files are produced](../reference/data.md).

## Complete the stages

| Stage | Finish when… | Continue with |
|---|---|---|
| Setup | Device addresses, measured fixture and chosen motion settings are recorded | [Set up the bench](../guide/configuration.md) |
| Recording | Runs have valid feedback, a consistent coordinate and acceptable timing | [Record motion](../guide/acquisition.md) |
| Fitting | Candidate models are saved with training scores | [Fit a model](../guide/identification.md) |
| Selection | A candidate explains validation runs and important residuals | [Compare candidates](../guide/identification.md#evaluate-and-inspect) |
| Final evaluation | Errors are reported for untouched test runs | [Evaluate the model](../guide/validation.md) |

Keep the selected model, run list, settings and software revision together. If you
use test results to change the model, those records have become development data;
collect new independent runs for the next final evaluation.

# Workflow

A study connects a mounted motor, its controller, a measured fixture and a declared
set of recordings. MotorFit supports five driver families, two control-input paths
and a pendulum rig. [Motor support](../reference/motors.md) describes the available
protocols and their validation coverage.

## Plan the experiment

Record the motor identity, controller mode and units, supply setting, coordinate
convention, fixture geometry and measured masses. Choose loads, gains, trajectories
and durations that cover the intended use. A longer run alone does not establish
accuracy; use independent conditions and repetitions.

Assign recordings to **training**, **model-selection validation** and **final test**
before fitting. Samples from the same trajectory are not independent experiments.
Keep those split assignments with the data.

## Keep the study together

Use an ignored local directory such as:

```text
data/my-motor/
  raw/train/             # completed recordings and their original evidence
  raw/validation/
  raw/test/
  processed/             # the same split structure after resampling
  candidates/            # fitted models and selection records
  results/               # fixed-model evaluations, plots and reports
```

Save the configuration, input hashes and runtime versions with the study. Keep
failed runs and their evidence too. Use `outputs/` for disposable demonstrations
or build products.

## Follow the stages

| Stage | Outcome | Guide |
|---|---|---|
| Configure | Model profile, measured fixture and per-device coordinate | [Configuration](../guide/configuration.md) |
| Record | Commands, feedback, timestamps and configuration snapshots | [Recording](../guide/acquisition.md) |
| Process and fit | Candidate parameters from the training recordings | [Identification](../guide/identification.md) |
| Select | A fixed model chosen on validation data | [Identification](../guide/identification.md#evaluate-and-inspect) |
| Evaluate | Final-test errors and supported simulator comparisons | [Validation](../guide/validation.md) |

Review completion, faults and timing before processing. In RobStride recordings,
`load` is firmware-reported nominal torque, not a shaft torque sensor. Preserve
independent wire captures when the study requires a separate timing audit.

## Freeze and report

Freeze the selected parameter file, split list, input hashes, controller and
fixture definitions, software versions and selection rule before final evaluation.
A later parameter or selection change starts a new study.

Report agreement with measurements separately from agreement between simulators.
Include the operating conditions, per-record errors and remaining unexplained
behavior. The [RS05 study](../case-studies/rs05.md) is a worked example with a
portable manifest and saved predictions. A manifest indexes prepared data; there
is no command that automatically designs the split or creates a complete study.

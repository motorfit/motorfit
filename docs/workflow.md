# From measurements to a validated model

This workflow targets a rotary actuator driving a known test fixture. QDD joints with an onboard position/velocity/torque controller are one application. The shipped integration uses RobStride CAN, an MIT-style PD law and a pendulum fixture. See [your motor](your-motor.md) for the implementation work needed when those assumptions differ.

## 1. Define the experiment

Record the controller mode and command units, motor identity, supply setting, coordinate convention, fixture geometry and measured masses. Use motion that covers the positions, velocities, loads and controller gains relevant to the intended use.

Separate training, model-selection validation and final evaluation recordings before fitting. A different load or gain can test generalization; repeated samples from the same trajectory should not be treated as independent experiments. Choose recording duration to cover excitation and the response of interest; see [trajectory timing](trajectories.md).

## 2. Configure and record

A setup in `configs/setups/` references a motor profile, a fixture, acquisition settings and a mounted device's local coordinate file. Relative references resolve against the setup file. The [acquisition guide](acquisition.md) describes inspection, zero calibration and recording commands.

Save raw commands, replies, timestamps, mode changes and the configuration snapshot along with the measured motion. Inspect recording completion, feedback faults and timing before processing. Keep independent wire captures when they are needed to check communication timing. The `load` field in the RobStride recorder is firmware-reported nominal torque.

## 3. Process with BAM

Use one raw-data directory per intended split. For example, after populating `outputs/my-motor/raw/train/` with completed recordings:

```bash
uv run motorfit process \
  --raw outputs/my-motor/raw/train --out outputs/my-motor/processed/train --dt 0.01
```

The command feeds complete recordings to the pinned BAM resampler and preserves metadata. Choose the resampling interval from the acquired timing and required model bandwidth. Preserve the original raw records alongside the processed inputs.

## 4. Fit and select

```bash
uv run motorfit fit --logdir outputs/my-motor/processed/train \
  --model m1 --trials 1000 --output outputs/my-motor/candidates/m1.json
```

The trial count above is an example budget, not an accuracy guarantee. BAM provides M1–M6; compare candidate families and repeated optimization runs on your declared validation sets. Record seeds, fitting options and objectives. This command fits only the supplied directory; it does not create or enforce a train/validation/test split for you.

After separately processing the validation split, evaluate a candidate without fitting:

```bash
uv run motorfit fit --logdir outputs/my-motor/processed/validation \
  --eval --output outputs/my-motor/candidates/m1.json
```

See [identification](bam-identification.md) for model loading, plots and the controller interpretation. Keep motor snapshots consistent across the recordings used in one fit.

## 5. Freeze and test

Freeze the selected parameter file, input hashes, split list, controller and fixture definitions, software versions and selection rule. Evaluate the final set with those fixed choices. Any later change to parameters or selection criteria starts a new study.

The supplied [RS05 study](case-studies/rs05.md) illustrates this with a portable dataset manifest, immutable model inputs and saved reference predictions. A manifest indexes an already prepared dataset; there is currently no command that automatically creates a complete new study or its split assignments.

## 6. Validate the model in use

First compare BAM predictions with measurements. Then replay the same initial conditions, recorded commands and fixed parameters in the relevant physics backend. Check timestep, delay, actuator disable events and friction handling alongside position error.

The included physics adapters implement M1 on the supported fixture equations. Other BAM families or physical rigs require corresponding simulator integration. Use the [validation guide](validation.md) for supported commands and keep model fit quality, cross-simulator agreement and unexplained physical residuals as separate results.

## Deliver a study

Organize a new study under its own motor identifier: configuration, raw and processed data, frozen model, reference predictions, metrics and a concise report. Include a small complete offline example so another user can check installation before loading the full dataset. Declare tested hardware and software versions and preserve failed or anomalous run evidence.

# BAM identification

MyActuator, HighTorque and Hexfellow use the same CLI with a recorded-effort adapter. See [their full workflow](effort-motors.md) for input scaling, zero-order-hold resampling and validation limits.

This project uses the unchanged Rhoban BAM submodule in `third_party/bam`, pinned by the repository. BAM owns M1–M6, resampling, its simulator, optimization and fitting plots. Local code supplies the RobStride MIT controller, fixture geometry and snapshot-aware entry points.

```bash
uv run motorfit process --raw examples/offline/raw --out outputs/processed --dt 0.01
uv run motorfit fit --logdir outputs/processed --model m1 --trials 20 --output outputs/example-m1.json
uv run motorfit plot --logdir outputs/processed --sim --params outputs/example-m1.json
```

These commands are an API demonstration using only three records. They do not repeat the formal 18-run, 360,000-evaluation model-selection study. The third-party fit flags are available through `motorfit fit --help`. A headless frozen-model example is provided by `motorfit demo`; use it for the first installation check.

The recorded nominal law is `Kp * (delayed_goal - q) + Kd * (goal_speed - dq) + feedforward`, clamped to the protocol torque range. `torque_ratio` maps that nominal output to effective torque. Quantized gains and encoded velocity/feedforward zeros are read from recordings. Only the position goal receives the identified fractional delay; disabling torque is a separate event. No periodic state reset is used in the frozen reference example.

Parameters include a complete motor snapshot. Load them using `motor_identification.identification.bam.load_model(path)`, so later TOML edits cannot change their interpretation. Frozen M1 is never the output destination of a new fit.

For your own experiment, process each split into a separate directory and pass only the training directory to `fit`. Use `fit --eval --logdir <validation-directory> --output <candidate.json>` to evaluate a fixed candidate. The CLI does not infer your experimental split. Freeze the selected model before evaluating the final recordings, and report the controller, fixture, seeds and selection rule alongside the parameters. See [the workflow](workflow.md).

The [RS05 reference study](case-studies/rs05.md) demonstrates this process with a declared split, M1–M6 selection evidence and frozen predictions. Its small bundled example is an installation and API exercise; it cannot reproduce that study's full parameter selection.

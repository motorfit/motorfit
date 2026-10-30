# MotorFit

**Record a motor. Identify its dynamics. Validate the model.**

MotorFit extends [Rhoban BAM](https://github.com/Rhoban/bam) with native motor
drivers, bench-data acquisition and model validation. Collect commands and measured
motion, identify actuator dynamics, and compare model predictions with recordings
and supported physics backends.

![MotorFit workflow: real experiments, parameter identification and simulation validation.](images/overview.png)

## Start with a complete example

[Install MotorFit and run the offline example](quickstart.md). Three recorded
experiments and a frozen model let you check the workflow without a motor or GPU.

When you are ready to collect data, follow [the experiment workflow](workflow.md)
and [configure your own motor](your-motor.md).

## What you can do

| Task | Guide |
|---|---|
| Choose a supported motor and connection | [Motor support](motors.md) |
| Collect commands, feedback and wire evidence | [Acquisition](acquisition.md) |
| Process data and fit BAM M1–M6 models | [Identification](bam-identification.md) |
| Evaluate a fixed model and compare physics backends | [Validation](validation.md) |
| Inspect a measured end-to-end application | [RS05 reference study](case-studies/rs05.md) |
| Extend drivers, controllers and fixtures | [Architecture](architecture.md) |

MotorFit is unreleased at **0.1.0**. The documentation is public; the source
repository currently requires access. The [Chinese introduction](https://github.com/motorfit/motorfit/blob/main/README.zh-CN.md)
provides the corresponding setup and project overview.

```{toctree}
:hidden:
:caption: Getting started

quickstart
workflow
your-motor
motors
```

```{toctree}
:hidden:
:caption: Record and identify

acquisition
effort-motors
trajectories
bam-identification
validation
```

```{toctree}
:hidden:
:caption: RS05 reference study

case-studies/rs05
fixture-masses
limitations
```

```{toctree}
:hidden:
:caption: Development and reference

architecture
environments
protocol-references
repository
documentation
```

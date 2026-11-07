# MotorFit

MotorFit identifies actuator dynamics from measured motion. Mount a motor on a
pendulum fixture, record its response to position commands, and fit a model that
predicts the motion under different loads and controller gains.

It supports **RobStride and Damiao** motors over Linux SocketCAN. MotorFit provides
the drivers, recording tools and simulation adapters; [Rhoban BAM](https://github.com/Rhoban/bam)
provides the friction models and optimizer.

![A pendulum experiment produces recordings, a fitted model and simulation comparisons.](images/overview.png)

## What you get

A fitted `model.json` contains friction, effective inertia, torque scaling,
command delay and coordinate-offset parameters. You can evaluate it against
recordings that were excluded from fitting, or replay a supported M1 model in
MuJoCo, Newton or mjlab.

The output is an actuator model for the measured operating conditions. MotorFit
currently models a single pendulum joint; it does not automatically calibrate an
entire robot or edit its XML. See [Parameters](reference/parameters.md) for the
physical meaning of the fitted values and their connection to simulation.

## Quickstart

[Follow the quickstart](getting-started/quickstart.md) to install MotorFit, record
motion from your bench and fit your first motor model.

## Identify your own motor

Follow the guides in order. Each uses the same configuration and study directory.

1. [Plan the experiment](getting-started/workflow.md): choose loads, motion and evaluation runs.
2. [Set up the bench](guide/configuration.md): describe the motor, fixture and connection.
3. [Record motion](guide/acquisition.md): establish the zero, collect runs and check their quality.
4. [Fit a model](guide/identification.md): process the data and compare candidate models.
5. [Evaluate the result](guide/validation.md): measure error on held-out runs and inspect residuals.

## Current support

| Capability | Available |
|---|---|
| Motor acquisition | RobStride private CAN protocol; Damiao MIT protocol |
| Identification | BAM M1–M6 friction models with torque-MIT control |
| Physics replay | M1 with the pendulum fixture |
| Hardware reference | One RS05 study; Damiao currently has software tests |

[Supported models](reference/motors.md) lists the shipped profiles.
[The RS05 study](case-studies/rs05.md) describes the experiment, selected parameters
and remaining prediction errors. Its [bundled replay](case-studies/rs05.md#reproduce-three-recorded-runs)
runs on a CPU using three recorded experiments.

The package is **0.1.0, unreleased**. The menu beside the logo selects the handbook
version. The documentation is public; the source repository currently requires
GitHub access.

```{toctree}
:hidden:
:caption: Getting started

Quickstart <getting-started/quickstart>
Workflow <getting-started/workflow>
```

```{toctree}
:hidden:
:caption: User guide

Setup <guide/configuration>
Record <guide/acquisition>
Fit <guide/identification>
Evaluate <guide/validation>
```

```{toctree}
:hidden:
:caption: Reference

Parameters <reference/parameters>
Motors <reference/motors>
Trajectories <reference/trajectories>
Data formats <reference/data>
Commands <reference/commands>
Backends <reference/backends>
Protocols <reference/protocols>
```

```{toctree}
:hidden:
:caption: RS05 example

Study <case-studies/rs05>
Fixture <case-studies/rs05-fixture>
Results <case-studies/rs05-findings>
```

```{toctree}
:hidden:
:caption: Development

Architecture <development/architecture>
Contributing <development/contributing>
```

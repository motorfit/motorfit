# Documentation

[Project overview](../README.md) · [Chinese overview](../README.zh-CN.md)

## Start here

1. [Run the offline example](../examples/offline/README.md) to inspect the inputs and outputs.
2. [Follow the workflow](workflow.md) from an experiment plan to a frozen, evaluated model.
3. [Bring your own motor](your-motor.md) to choose a configuration or implement a new adapter.

## Use the tools

| Guide | What it covers |
|---|---|
| [Motor support](motors.md) | Models, connection paths, units and validation coverage |
| [Acquisition](acquisition.md) | Setup composition, coordinates, commands and recorded evidence |
| [Effort-controlled motors](effort-motors.md) | MyActuator, HighTorque and Hexfellow setup and BAM evaluation |
| [Protocol references](protocol-references.md) | Manufacturer documentation used by the drivers |
| [Trajectories](trajectories.md) | Excitation duration, observation windows and video timing |
| [Identification](bam-identification.md) | Processing, fitting, held-out evaluation and model snapshots |
| [Validation](validation.md) | BAM reference checks, M1 physics replay and benchmark diagnostics |
| [Environments](environments.md) | Core install and optional backend versions |

## Understand and extend

- [Repository layout and tracking policy](repository.md): source, fixture and local archive boundaries.
- [Architecture](architecture.md): device, controller, rig and dataset boundaries; project naming.
- [RS05 reference study](case-studies/rs05.md): one complete application of the workflow.
- [RS05 fixture properties](fixture-masses.md) and [measured limitations](limitations.md).

## Language policy

English is the default for `README.md`, technical guides, new examples and CLI documentation. `README.zh-CN.md` provides the corresponding Chinese introduction and entry points. Changes to setup commands, scope or examples should update both introductions together. Additional translations use an explicit language suffix and link to their English counterpart.

Original recordings, research reports and validated videos retain their recorded language and bytes. Translated guides explain those artifacts without rewriting the evidence.

# Configuration

Choose the [connection path](../reference/motors.md) from the controller protocol and control law. RobStride and Damiao have native acquisition adapters for the torque-based MIT law.

## Configure the mounted assembly

Copy a setup inside [`configs/setups/`](https://github.com/motorfit/motorfit/tree/main/configs/setups) so its references stay valid. Use `rs05_pendulum.toml` for RobStride or `dm4310_pendulum.toml` for Damiao, then edit:

| Input | What to measure or select |
|---|---|
| Motor profile | Exact model, protocol mapping and firmware; profiles are in `configs/motors/<family>/` |
| Device | CAN channel, motor address, feedback/host address and timeout |
| Fixture | Tip mass, length, arm mass, center of mass, inertia and hub inertia |
| Acquisition | Excitation, amplitude, duration, sample rate and fixed gains |
| Supply | Configured voltage; this is not a synchronous voltage measurement |
| Coordinate | A distinct ignored file for this mounted device's software zero |

Read and inspect the device, then establish the coordinate at a known physical angle. The supplied gains and fixture describe examples, not commissioned settings for another assembly. [Acquisition](acquisition.md) gives the command sequence.

The fitter uses the full motor definition saved in each recording. A new compatible model name does not require a new friction model. Protocol ranges are encoding limits, not measured output-torque limits. Damiao runtime PMAX/VMAX/TMAX must match the profile.

## Freeze a reusable result

Keep each motor's model and dataset in its own directory. Preserve its UID or identity, coordinates, controller settings and fixture with the recordings. Parameter JSON must retain the full motor definition. Never substitute the bundled RS05 M1 for a new motor's fit.

For a portable study, follow the [example manifest](https://github.com/motorfit/motorfit/blob/main/tests/fixtures/offline/manifest.json): relative paths, explicit splits, model/recording hashes and reference predictions. The current plots use pendulum load labels such as `mass_g`; other rigs need corresponding presentation metadata. See the [workflow](../getting-started/workflow.md) for split and evaluation discipline.

For a new protocol, controller law or fixture equation, see [extension points](../development/architecture.md#extension-points).

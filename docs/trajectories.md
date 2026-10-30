# Trajectories and video timing

Recording duration is an experiment setting. Choose it to excite the actuator over the intended operating range and to observe settling, release or reversal behavior. The 20-second recordings in the reference study are one protocol choice.

## Configurable Python acquisition

[`Trajectory`](../src/motor_identification/acquisition/trajectories.py) wraps BAM's built-in trajectories. `duration_s` in the acquisition TOML, or `motorfit record --duration`, selects the duration. Built-in BAM trajectories are rescaled in time; `amplitude` scales their angles. The recording preserves the selected duration, native duration and time scale.

The included `bam_6s.toml` example uses 6 seconds. `chirp.toml` uses the 30-second `soccer_sweep` from [soccer-bam](https://github.com/utra-robosoccer/soccer-bam/tree/96fe9a971d02cee33913d1bbb0b6cf37575f43b7), whose formula is `amplitude * sin(sweep_k * t²)`. For this sweep, changing duration changes the observation interval; it does not renormalize `sweep_k`.

Time scaling changes velocities, accelerations and frequency content. Pick duration together with amplitude, gains, sampling rate, fixture load and the intended validation conditions. A longer recording can cover settling or slower effects; it does not by itself establish model accuracy. Use multiple trajectories and independent operating conditions.

## RS05 reference acquisition

The supplied RS05 dataset was recorded with a C++ collector using the following timing:

| Trajectory | Schedule | Nominal total |
|---|---|---:|
| `sin_time_square`, `sin_sin`, `up_and_down` | 2 s initial hold + 12 s excitation + 4 s return + 2 s final hold | 20 s |
| `lift_and_drop` | 2 s initial hold + 4 s lift + 14 s torque-disabled observation | 20 s |
| `long_sweep` | 2 s initial hold + 30 s excitation + 4 s return + 2 s final hold | 38 s |

The schedule contains 2,001 or 3,801 timestamps at 100 Hz, including the final nominal endpoint. These are properties of the recorded experiment. The current Python recorder uses the configurable duration described above; choosing 20 seconds does not reproduce these staged schedules.

The initial/final holds provide observation windows around motion. The lift/drop protocol keeps collecting feedback while the actuator is disabled. The long sweep supplies an additional extended test. These choices describe the recorded experiment; a new actuator study should select and document its own windows.

## How replay duration is calculated

The renderer uses the saved processed samples at their recorded `dt`, at 1× speed:

```text
source duration = number of processed samples × dt
video frames    = ceil(source duration × 30 fps)
video duration  = video frames / 30 fps
```

The last sample is held through its final display interval. Video duration is rounded up to a whole frame. Videos cover the complete processed record; no fixed 20-second crop is applied. Position interpolation is for display only and does not rerun the simulator.

The 18 supplied videos were checked against their metadata and container frame counts:

| Load | Four ordinary clips | Long sweep | Five-clip compilation |
|---|---:|---:|---:|
| 100 g | 20.000 s each | 38.000 s | 118.000 s |
| 200 g | 20.000 s each | 38.033 s | 118.033 s |
| 500 g | 20.000 s each | 38.000 s | 118.000 s |

The 200 g long recording has 3,801 processed samples at 0.01 s: a 38.01 s display window, rounded to 1,141 frames. The other long clips have 3,800 processed samples and 1,140 frames. The compilation concatenates all five full clips. See the [RS05 study](case-studies/rs05.md) for video links and the scope of the predictions shown.

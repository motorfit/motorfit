# Trajectories

Recording duration is an experiment setting. Choose it to excite the actuator over the intended operating range and to observe settling, release or reversal behavior. The 20-second recordings in the reference study are one protocol choice.

## Configurable Python acquisition

[`Trajectory`](https://github.com/motorfit/motorfit/blob/main/src/motorfit/acquisition/trajectories.py) wraps BAM's built-in trajectories. `duration_s` in the acquisition TOML, or `motorfit record --duration`, selects the duration. Built-in BAM trajectories are rescaled in time; `amplitude` scales their angles. The recording preserves the selected duration, native duration and time scale.

The included `bam_6s.toml` example uses 6 seconds. `chirp.toml` uses the 30-second `soccer_sweep` from [soccer-bam](https://github.com/utra-robosoccer/soccer-bam/tree/96fe9a971d02cee33913d1bbb0b6cf37575f43b7), whose formula is `amplitude * sin(sweep_k * t²)`. For this sweep, changing duration changes the observation interval; it does not renormalize `sweep_k`.

Time scaling changes velocities, accelerations and frequency content. Pick duration together with amplitude, gains, sampling rate, fixture load and the intended validation conditions. A longer recording can cover settling or slower effects; it does not by itself establish model accuracy. Use multiple trajectories and independent operating conditions.

See the [RS05 recording schedule](../case-studies/rs05.md#rs05-reference-acquisition) for the historical experiment and video timing.

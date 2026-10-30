# Trajectories

A trajectory returns a target angle and a torque-enable flag. Targets are expressed
relative to the saved physical zero. Select a trajectory in the motion TOML or with
`record --trajectory NAME`.

## Available motions

The BAM trajectories have a native duration of 6 seconds. Define native time
`u = 6t / T`, where `T` is the requested `duration_s`, and amplitude multiplier `A`.

| Name | Target before multiplying by `A` | Enable behavior |
|---|---|---|
| `sin_time_square` | `sin(u²)` | Enabled throughout |
| `sin_sin` | `(π/2) sin(u) + 0.5 sin(5u) sin(2u)` | Enabled throughout |
| `up_and_down` | Smooth cubic path: `0 → π/2 → 0.8π/2` | Enabled throughout |
| `half_sine` | `(π/2) sin(u/2)` | Enabled throughout |
| `steps` | Piecewise constant: `0, 0.75, 1.55, 0.75, 0` rad | Enabled throughout |
| `lift_and_drop` | Smooth cubic move from `0` to `−π/2` in the first third of the run | Disabled from `T/3` onward |
| `nothing` | Zero target | Disabled throughout |
| `soccer_sweep` | `sin(sweep_k × t²)` using actual time `t` | Enabled throughout |

For `up_and_down`, the intermediate peak occurs at `T/2` and the final target is
`0.8π/2`. `half_sine` reaches its peak near `0.524T` and ends at
`(π/2) sin(3)`; it does not finish at `π/2`. The step transitions occur at
`T/6`, `2.5T/6`, `4T/6` and `5T/6`.

## Amplitude

`amplitude` multiplies the angle; it does not constrain every motion to that number
of radians. For example:

- `sin_time_square` with `amplitude = 0.2` stays within ±0.2 rad.
- `lift_and_drop` with `amplitude = 0.2` lifts to `−0.2 × π/2 ≈ −0.314 rad`.
- `sin_sin` combines two terms, so its envelope differs from either example.

Check the complete trajectory against the available travel before recording.

## Duration and speed

Changing `T` rescales the BAM trajectories in time. Doubling duration preserves the
angle path while halving target velocities and quartering target accelerations.
Release in `lift_and_drop` also moves from 2 seconds at the native duration to `T/3`.

`soccer_sweep` behaves differently:

$$q_d(t)=A\sin(kt^2),\qquad f(t)=kt/\pi.$$

Its `sweep_k = k` stays fixed when duration changes. A longer run reaches a higher
frequency; it does not stretch the same path. The shipped `chirp.toml` uses
`T = 30 s` and `k = 0.1`, reaching about 0.955 Hz at the end.

## Choose a trajectory for the experiment

Use a smooth sweep to inspect tracking across speeds. Add slow reversals or
`up_and_down` to examine near-static behavior. Use `lift_and_drop` when passive
release and stopping are part of the intended task. A `nothing` run observes
passive motion with torque disabled for the entire run.

Command-line values override the motion file for one recording:

```bash
uv run --no-sync motorfit record --setup configs/local/bench.toml \
  --trajectory sin_time_square --duration 20 --amplitude 0.2 \
  --out data/my-motor/raw/pilot/sweep-20s
```

The example assumes the bench and gains have already been commissioned. All
resolved values and time-scaling metadata are saved in `raw.json`.

## Relation to the RS05 dataset

The historical RS05 collector added initial holds, returns and final holds around
its excitation windows. Setting the Python recorder to 20 seconds does not recreate
that schedule. [RS05 acquisition timing](../case-studies/rs05.md#rs05-reference-acquisition)
documents the recorded experiment separately.

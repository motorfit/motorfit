# Simulation backends

Use BAM for fitting and model evaluation. Use a physics backend when you need to
check that an M1 implementation reproduces the identified actuator behavior in
another simulation environment.

| Backend | Current use | Runtime |
|---|---|---|
| BAM | M1–M6 fitting, evaluation and plots | Core environment; CPU |
| MuJoCo | M1 pendulum replay and release-event studies | `simulation` extra; CPU |
| Newton | M1 replay through `SolverMuJoCo` | Separately managed Newton runtime |
| mjlab / MJWarp | Batched M1 pendulum replay | Separately managed runtime with CUDA |

All three MotorFit physics adapters implement the same torque-MIT controller,
fractional position-command delay and pendulum geometry. M2–M6 and other rigs need
additional physics integration.

## BAM and MuJoCo

The root `uv.lock` describes the Python 3.12 environment. Install it once and run
commands without resynchronizing:

```bash
uv sync --frozen --extra simulation
uv run --no-sync motorfit replay \
  --dataset tests/fixtures/offline/manifest.json \
  --engine mujoco --dt 0.002 --output outputs/mujoco-replay
```

The `simulation` extra currently installs MuJoCo **3.17.0**. Without that extra,
the core installation still supports acquisition, processing, BAM fitting and the
offline demo. Neither BAM nor CPU MuJoCo replay requires a GPU.

The [evaluation guide](../guide/validation.md#replay-in-a-physics-backend) explains
replay outputs. `--dt` must divide the processed sample interval.

## Newton and mjlab

These runtimes are not included in the core lockfile. Use an environment with the
backend's compatible dependencies, outside the project `.venv`. Expose MotorFit's
source tree to that interpreter:

```bash
PYTHONPATH="$PWD/src" /path/to/backend/bin/python \
  -m motorfit.identification.validate_simulation \
  --dataset tests/fixtures/offline/manifest.json \
  --engine mjlab --dt 0.002 --output outputs/mjlab-replay
```

Replace `/path/to/backend/bin/python` with the actual interpreter. Use
`--engine newton` and another output directory for Newton.

The Newton adapter needs NumPy, MuJoCo, Newton and Warp. It uses Newton model import
and controls with `SolverMuJoCo`'s CPU path. Consequently, it checks the Newton
integration rather than providing independent Featherstone dynamics.

The mjlab adapter additionally uses mjlab, MuJoCo Warp and Torch on a CUDA device.
It batches recordings with matching fixture geometry. Requested solver options
are checked against the available GPU runtime; unsupported options can cause the
replay to fail rather than silently changing the comparison.

This repository does not provide a tested, general-purpose installation recipe
for those external environments. Keep their package and source revisions with
any replay results.

## Additional tools

| Task | Extra system requirements |
|---|---|
| Release-event replay | C++17 compiler; the helper links against the installed MuJoCo |
| Replay video rendering | ffmpeg and a working OpenGL/EGL runtime |
| Interactive BAM plots | A graphical Matplotlib backend |

These tools are unnecessary for the offline demo and ordinary fitting.

## Reproducing an archived comparison

The full RS05 archive includes package inventories and revisions in
`data/rs05/environments/`. Its earlier CAD comparison used MuJoCo 3.8. The later
CPU/GPU comparison used Python 3.13.11, mjlab 1.6.0, MuJoCo/MJWarp 3.17.0,
Warp 1.17.0, Torch 2.9.0 and NumPy 2.3.4.

That experiment explicitly overrode mjlab 1.6.0's declared `~=3.11.0` engine
constraint. Its inventory documents how the saved result was produced; it is not
a conflict-free lockfile for a new installation. Replaying with different versions
creates a new comparison, which should retain its own `protocol.json`.

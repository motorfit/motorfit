# Backends

MotorFit's standard environment is Python 3.12 with the dependencies pinned in
`uv.lock`. Keep the main application and its development tools in `.venv/`.

| Backend | Use | Environment |
|---|---|---|
| BAM | Process recordings, identify M1–M6 and evaluate fitted models | Core install, CPU |
| MuJoCo | Replay supported M1 torque-MIT models and release events | `simulation` extra, CPU |
| Newton | Replay M1 through Newton's MuJoCo solver integration | Separate compatible runtime |
| mjlab / MJWarp | Batched M1 replay | Separate compatible runtime and CUDA GPU |

## Core and MuJoCo

```bash
uv sync --frozen
uv sync --frozen --extra simulation
```

The first command installs the core; the second adds MuJoCo 3.17.0. BAM fitting and
the offline demo do not need a GPU. Use `--extra simulation` on `uv run` commands
that need MuJoCo, or use `--no-sync` once the chosen environment is installed.

Release-event replay additionally needs a C++17 compiler. Video rendering needs
ffmpeg and an OpenGL/EGL runtime. These system tools are separate from Python
packages. The [development setup](../development/contributing.md#development-environment)
adds testing and documentation tools to the same `.venv`.

## Newton and mjlab

These adapters are optional. Their runtime constraints differ from the core and
are not part of its lockfile. Use a compatible, independently managed environment
outside this checkout and expose this source tree through `PYTHONPATH`:

```bash
PYTHONPATH="$PWD/src" /path/to/backend/bin/python \
  -m motorfit.identification.validate_simulation \
  --dataset tests/fixtures/offline/manifest.json --engine mjlab \
  --dt 0.002 --output outputs/mjlab
```

Replace the interpreter path and engine with the installed backend. Python modules
use the `motorfit` namespace. Optional replay does not require installing the
Python-3.12-only core distribution into another Python version.

Both adapters currently implement the supported M1 torque-MIT controller and
pendulum equations. Other BAM families need their own
physics integration. Newton's current adapter uses `SolverMuJoCo`; it is not an
independent Featherstone validation. See [Validation](../guide/validation.md).

## Recorded study environments

The [RS05 archive](../case-studies/rs05.md) records the exact packages and source
revisions used for its comparisons under `data/rs05/environments/`.
The historical CAD baseline used MuJoCo 3.8; the later MJWarp 3.17 study used Python
3.13.11, mjlab 1.6.0, MuJoCo/MJWarp 3.17.0, Warp 1.17.0, Torch 2.9.0 and NumPy 2.3.4.
That mjlab release declared a `~=3.11.0` engine constraint, which the study explicitly
overrode. Its package inventory is provenance, not a general installation lockfile.

A newly installed runtime produces a new comparison. Preserve the recorded engine
versions with the original results instead of relabelling archived predictions.

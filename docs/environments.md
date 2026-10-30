# Environments

Core: Python 3.12, fixed Rhoban BAM source, NumPy 2.3.4, Optuna 4.3, and the exact versions in the root `uv.lock`. `uv sync --frozen` and the BAM demo need no GPU or MuJoCo. `uv sync --frozen --extra simulation` adds MuJoCo 3.17.0 for CPU replay and event alignment. A C++17 compiler is needed only for the event replay helper; acquisition uses Python. Video rendering additionally needs ffmpeg and an OpenGL/EGL-capable runtime.

The historical CAD comparison used MuJoCo 3.8 and backend-specific runtimes; its saved outputs keep those version records. Replaying with a different engine version is a new comparison, not a relabel of the archived prediction files.

The verified MJWarp 3.17 study used Python 3.13.11, mjlab 1.6.0, MuJoCo/MJWarp 3.17.0, Warp 1.17.0, Torch 2.9.0 and NumPy 2.3.4. That mjlab release declares a `~=3.11.0` engine constraint; the study explicitly overrode it. The local archive keeps the recorded package list and source revisions in `data/rs05/environments/` as provenance. Do not treat that as a conflict-free general installation specification or mix it into the core lockfile.

Optional backend replay modules can be used from their independently managed environment with this checkout's `src` on PYTHONPATH. Core BAM fitting remains on Python 3.12. The recorded environment JSON files describe the original benchmarks; they are not lockfiles for a fresh installation.

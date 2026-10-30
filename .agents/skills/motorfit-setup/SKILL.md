---
name: motorfit-setup
description: Install MotorFit and run its bundled offline example. Use for first-time setup, missing BAM dependencies, or choosing a core or optional simulation environment.
---

# Set up MotorFit

Run commands from the MotorFit repository root. Resolve the checkout containing this skill before using relative paths; the skill may be loaded through a discovery symlink.

## Install and check the core

1. Inspect [pyproject.toml](../../../pyproject.toml), [environment guidance](../../../docs/environments.md) and the current environment. Core processing and BAM fitting require Python 3.12 and `uv`; use the committed `uv.lock` without upgrading dependencies.
2. Check `git submodule status -- third_party/bam`. If BAM is uninitialized, run `git submodule update --init --recursive`. Use the revision recorded by this checkout, preserve local submodule edits, and do not use `--remote`. A source archive without BAM needs the matching source before installation.
3. Install and run the headless example below. Choose a new output directory if the example destination already exists.

```bash
uv sync --frozen
uv run --frozen motorfit demo \
  --dataset examples/offline/manifest.json --output outputs/setup-check
```

The demo opens no CAN connection and needs no motor or GPU. It verifies three complete recordings and reproduces their saved BAM predictions with a frozen model. This checks installation; it does not reproduce the full RS05 model-selection study.

## Choose an optional environment

- For requested MuJoCo replay, use `uv sync --frozen --extra simulation` and retain `--extra simulation` on subsequent `uv run` commands that need it.
- For Newton or mjlab, read the backend section of [environments.md](../../../docs/environments.md). Use a separately managed compatible environment and expose this checkout's `src` on `PYTHONPATH`. Historical version reports are provenance, not fresh-install lockfiles; do not copy their overrides into the core lock.
- Install rendering or C++ build dependencies only when the requested workflow needs video or release-event replay.

## Completion

Confirm that the demo exits successfully and produces `comparison.png`, `metrics.csv`, `summary.json` and three trajectory `.npz` files. Inspect the summary for finite metrics, reproduced references and `parameters_refitted: false`. Report the environment used and link the output plot and summary. If installation fails, report the failing command and concrete dependency or access issue.

## Maintenance sources

- [Offline example](../../../examples/offline/README.md) and [demo implementation](../../../src/motor_identification/offline.py): inputs, output names and reference checks.
- [Project configuration](../../../pyproject.toml), [lockfile](../../../uv.lock) and [submodules](../../../.gitmodules): dependency and source versions.

Recheck these sources when installation commands or supported runtimes change.

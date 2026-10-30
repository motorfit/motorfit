# Offline validation

Use [the workflow](workflow.md) to prepare and freeze a new study. The commands below use the separately stored [RS05 study](case-studies/rs05.md#what-to-reproduce). For a fresh checkout, start with the self-contained [offline example](../examples/offline/README.md). `verify` checks the saved dataset manifest; `audit-feedback` and the release-event analysis implement the reference RS05 wire-capture conventions. Other capture formats need their corresponding audit implementation.

`uv sync --frozen` installs the Python 3.12 core. None of the following commands opens CAN. Every output directory must be new. The complete-data commands require the data attachment.

```bash
uv run motorfit verify --dataset data/rs05/formal-v3/manifest.json
uv run motorfit audit-feedback --dataset data/rs05/formal-v3/manifest.json --output outputs/audit
```

Verification checks all 111 raw/processed recordings, reference predictions, frame sources, M1 and the fixed split. The feedback audit independently decodes CAN words, compares the independent capture, reconstructs interpolation and extracts STOP/reply events. If static snapshots are present it also audits all 111 pre-run captures and the recorded firmware facts.

## M1 physics replay

The included physics adapters implement frozen M1 with the recorded MIT-style controller and pendulum dynamics. BAM fitting supports M1–M6; replaying another family or rig requires the corresponding physics integration. A new manifest alone does not supply that integration.

```bash
uv sync --frozen --extra simulation
uv run --frozen --extra simulation motorfit replay \
  --dataset data/rs05/formal-v3/manifest.json --engine mujoco --dt 0.002 \
  --scene-assets data/rs05/assets/bench --output outputs/cad-replay
```

Without `--scene-assets`, replay uses the equivalent point-load fixture used for fitting. `--fixture-model identified_point` gives the CAD appearance with identification-equivalent inertia. `--ablations` evaluates delay/friction/armature removal on the training split.

```bash
uv run --frozen --extra simulation motorfit replay \
  --dataset data/rs05/formal-v3/manifest.json --engine mujoco --dt 0.002 \
  --scene-assets data/rs05/assets/bench --options configs/simulation/asroballet-option.xml \
  --friction default --output outputs/solver-default
```

The option fragment is a standalone benchmark configuration; no robot XML is edited. `--friction original` retains the benchmark friction constraint. The common replay entry supports `--engine newton` and `--engine mjlab` when the matching optional environment is provided. It checks requested options instead of quietly disabling unsupported features. Optional runtime versions and limitations are documented in [the environment guide](environments.md).

## Release timing

```bash
uv run --frozen --extra simulation motorfit release-replay \
  --dataset data/rs05/formal-v3/manifest.json --scenes data/rs05/scenes/release \
  --output outputs/release-alignment
```

This builds a small C++ helper with the installed MuJoCo library and runs the 27 release records at 62.5 microseconds for the processed enable flag, STOP send and two acknowledgments. Use `--record <id>` for a single record; `--dt 0.000125` or `0.00025` for timestep comparisons. Bus-clock variants are available through `--cases stop_tx_bus stop_ack1_bus stop_ack2_bus`. The helper splits an integration step at the event without an extra command-delay shift. The model and measured trajectories stay fixed. These times are sensitivity assumptions, not measurements of the power stage's actual current decay.

`pytest` includes relocation/tamper checks, an analytical event-impulse test and comparison with four sealed representative release trajectories. Core tests run without MuJoCo; optional MuJoCo/Newton/mjlab tests skip when their runtime is absent. CAD tests additionally require `data/rs05/assets/bench/` or `MOTORFIT_RS05_ASSETS` pointing to an extracted bench asset directory. Skipped tests are not passes.

## Rendering and result checks

```bash
MUJOCO_GL=egl uv run --extra simulation python scripts/render_replay.py \
  --dataset data/rs05/formal-v3/manifest.json --source data/rs05/results/replay/cad-baseline \
  --assets data/rs05/assets/bench --output outputs/video --grams 200 \
  --trajectory lift_and_drop --preview 8
```

The renderer uses saved states from all three backends and a common camera. Omitting `--preview` writes a full video; ffmpeg is required. With all loads/trajectories selected, `--concat` also builds three full-length compilations. The renderer has a portable bundled Matplotlib font fallback; `--font` accepts a preferred font file. The provided Chinese videos remain the original validated outputs and are not relabelled as timing-corrected runs.

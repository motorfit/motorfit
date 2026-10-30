# Contributing

This page is the maintenance reference for code, test data and documentation.
For using MotorFit, begin with [Quickstart](../getting-started/quickstart.md).

## Directory layout

| Location | Contents |
|---|---|
| `src/motorfit/` | Installable Python package and `motorfit` command |
| `configs/` | Reusable motor, fixture and acquisition templates |
| `tests/` | Protocol, recording, fitting and replay checks |
| `tests/fixtures/offline/` | Three portable recordings, a frozen model and reference predictions |
| `docs/` | Sphinx/MyST handbook and published illustrations |
| `scripts/` | CAD/figure utilities and documentation publishing |
| `third_party/bam/` | Unmodified BAM submodule at the committed revision |
| `.agents/skills/` | Shared coding-agent workflows |

Local work has three homes: `data/<study>/` for complete experiments, `outputs/`
for disposable builds and trial runs, and `configs/local/` for mounted-device
coordinates. These directories are ignored in full. The project environment is
`.venv/`, also ignored. Keep recordings, models, plots, CAD and runtime provenance
for the same study together under its `data/` directory.

The offline fixture is used by both the quickstart and the regression test. Its
internal paths are relative, so the directory can be copied intact. Write new fits
and predictions to a new study or output directory. Test fixtures should be small,
consumed by an actual test, and accompanied by an explanation of their purpose.

## Development environment

Initialize the submodule, then install the development tools, documentation and
CPU simulation dependencies in one environment:

```bash
git submodule update --init --recursive
uv sync --frozen --extra simulation --group docs
uv run --no-sync ruff check src tests scripts docs/conf.py
uv run --no-sync pytest -q
```

Use `--no-sync` after this setup so individual tool commands do not change the
installed extras. After dependency changes, repeat the sync command. Keep the
committed lockfile and version `0.1.0` until a release is deliberately prepared.
Newton and mjlab use externally managed environments; see [Backends](../reference/backends.md).

Tests cover wire encoding and reply matching, recording failure/shutdown behavior,
configuration and dataset integrity, BAM fitting, and analytical replay behavior.
The offline test invokes the installed command entry point and checks relocated
fixtures and modified inputs. Optional Newton/mjlab tests skip when their runtimes
are absent; they are not evidence of GPU or hardware validation in ordinary CI.

Keep tests focused on distinct failure modes. Test shared codecs with representative
profiles and independent expected bytes; repeat by model or firmware only when the
encoding or behavior differs. Run the complete fitting pipeline once per control
source (MIT or recorded effort). Avoid duplicating an integration check with mocks
or retesting upstream physics; retain failure cleanup and data-integrity checks.

## Documentation structure

Every page has one role and one place in the sidebar:

| Directory | Purpose |
|---|---|
| `getting-started/` | Installation and the end-to-end workflow |
| `guide/` | Task instructions: configure, record, identify and validate |
| `reference/` | Device support, trajectory behavior, backends and protocol sources |
| `case-studies/` | Recorded experiments, measured fixture facts and findings |
| `development/` | Architecture, extension points and project maintenance |

Write Markdown with MyST directives where needed. Add a page to the appropriate
toctree in `docs/index.md`; give its sidebar entry a short task or topic name.
Use relative links between handbook pages and full GitHub links for source files.
When a published page moves, add its former URL to `redirects` in `docs/conf.py`.

Keep commands in the user guides authoritative. README files provide a short
introduction and quickstart, and link to the handbook for details; update their
English and Chinese commands together. Keep reusable guidance separate from
RS05-specific settings and measurements. New technical pages use English.

## Preview the handbook

After the development sync above:

```bash
uv run --no-sync sphinx-build -W --keep-going -b html \
  -d outputs/docs-doctrees docs outputs/docs
python3 -m http.server 8000 --directory outputs/docs
```

Open `http://localhost:8000/`. Check links, sidebar navigation, search and the page
at a narrow browser width. Generated HTML stays in `outputs/`. When changing the
page layout, use a fresh build directory to avoid stale pages from an older build.

## CI and publication

The **Code** workflow checks for tracked ignored files, runs Ruff and executes
pytest with the core and MuJoCo dependencies. Documentation-only edits do not run
this workflow. The **Documentation** workflow builds relevant changes with Sphinx
warnings treated as errors. It installs only documentation dependencies in the
runner and does not need a motor, GPU or initialized BAM submodule.

Before committing, inspect `git diff --cached --stat` and `git diff --cached --check`.
`git ls-files --cached --ignored --exclude-standard` should return no paths.

After committing and pushing documentation changes, publish from the repository root:

```bash
bash scripts/publish_docs.sh
```

The script makes a fresh build in a temporary environment, pushes the rendered
files to `motorfit/motorfit.github.io`, and removes its temporary environment.
GitHub Pages deploys the site repository's `main` branch. The source repository
remains private; only rendered documentation and static assets are published.

Publication uses the maintainer's existing local SSH access. The organization
disables deploy keys, so the source CI has no cross-repository deployment secret.

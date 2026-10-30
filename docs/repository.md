# Repository layout and tracking policy

| Location | Contents | Git |
|---|---|---|
| `src/`, `scripts/` | Reusable implementation and utilities | Tracked |
| `configs/` | Reusable motor, fixture and acquisition templates | Tracked, except `local/` |
| `examples/offline/` | Three fixed recordings, one model, references and manifest | Explicit allowlist |
| `tests/fixtures/release/` | One scene, event times and four regression predictions | Explicit allowlist |
| `docs/`, `skills/` | Guides, shared agent skills and four published figures | Tracked |
| `third_party/bam/` | Upstream BAM at a fixed commit | Git submodule |
| `data/<study>/` | All materials belonging to a local experiment | Ignored in full |
| `outputs/` | Temporary runs, renders, builds and checks | Ignored in full |
| `configs/local/` | Mounted-device identity and physical coordinates | Ignored in full |

Keep an experiment's recordings, models, results, CAD, scenes and runtime snapshots together in
`data/<study>/`. The [RS05 archive](case-studies/rs05.md#what-to-reproduce) illustrates this layout.
The old root `results/`, `models/`, `assets/` and `environments/` locations are also ignored to
prevent accidental reintroduction. Documentation retains only images it actually uses; figure
prompts, reference renders and intermediate outputs belong to the experiment archive.

The offline example is self-contained. Its data, frozen model and reference predictions are
deliberate small fixtures. Copy that directory to use it elsewhere. New fits and output files
must go to a new path under `data/<study>/` or `outputs/`; never overwrite a frozen fixture.

## Before committing

Enable the repository hook once per clone:

```bash
git config core.hooksPath .githooks
```

Stage named source paths, then inspect and check the staged tree:

```bash
git diff --cached --stat
python3 scripts/check_repository.py
git diff --cached --check
```

The hook checks the Git index, including forced additions and previously tracked ignored files.
GitHub CI repeats that check and runs lint, tests and the offline example from a fresh checkout.
The checker permits source extensions in designated directories and explicitly lists example
records, regression artifacts and documentation images. It also limits each blob to 5 MiB and
the source/fixture total to 20 MiB (the BAM submodule has its own history).

Adding a new intentional fixture requires reviewing and updating the allowlist in
`scripts/check_repository.py` along with its consumer and documentation. Do not expand it for
ordinary experiment outputs or bypass the hook to upload local archives.

Adding an ignore rule does not untrack existing files or remove their history. If an experiment
file was accidentally staged, unstage it and keep the local copy. History cleanup requires a
separate, deliberate rewrite and a verified backup outside the repository.

# Working on MotorFit

- Python source and imports use `motorfit`; the package lives in `src/motorfit/`.
- Keep experiments under ignored `data/<study>/`, temporary output under `outputs/`,
  and device coordinates under `configs/local/`. Never commit environments or generated files.
- Reusable test data belongs in `tests/fixtures/`. Preserve the bundled offline recordings,
  hashes and frozen predictions when changing paths or packaging.
- Use the single project environment `.venv`: `uv sync --frozen --extra simulation --group docs`.
  Run tools with `uv run --no-sync` after syncing. Optional backend environments are external.
- Check changed Python with Ruff and run the relevant tests; run the full suite after package
  or dependency changes. Build changed docs with Sphinx warnings treated as errors.
- See `docs/development/contributing.md` for commands, directory roles and documentation rules.
  Stage named paths and inspect the staged diff before committing.
- Keep the unreleased version at `0.1.0` and the English/Chinese README commands consistent.
  Shared skills live in `.agents/skills/`; `.claude/skills` is its relative discovery symlink.

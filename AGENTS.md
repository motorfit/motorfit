# Repository working rules

- Read `docs/repository.md` before changing the layout or Git tracking.
- Store complete local experiments under `data/<study>/`; use `outputs/` for temporary runs.
  Keep device coordinates in `configs/local/`. These directories are ignored in full.
- The offline example, release regression fixtures and four published documentation images
  are the only approved data/artifact exceptions. Do not add experiment materials to other
  source directories or widen the allowlist without an explicit fixture need.
- Enable the commit hook with `git config core.hooksPath .githooks`. Stage named paths, inspect
  `git diff --cached --stat`, and run `python3 scripts/check_repository.py` before committing.
- Keep the unreleased package version at `0.1.0`. Keep English and Chinese README commands
  consistent. Shared agent skills live directly in `.agents/skills/`; `.claude/skills` is a relative
  symlink to that directory. Do not add a root-level `skills/` directory.

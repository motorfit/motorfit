"""Check the Git index against the source-only repository policy (stdlib only)."""

import subprocess
import sys
from pathlib import PurePosixPath

ROOT_FILES = {
    ".gitignore",
    ".gitmodules",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "README.zh-CN.md",
    "pyproject.toml",
    "uv.lock",
    "docs/conf.py",
    "docs/_templates/global-nav.html",
}
SOURCE_SUFFIXES = {
    "src": {".py", ".cpp", ".h", ".hpp"},
    "configs": {".toml", ".xml"},
    "scripts": {".py", ".sh"},
    "tests": {".py"},
    "docs": {".md"},
    ".github": {".yml", ".yaml"},
}
RECORDS = (
    "100g_09_v3_100g_r01_sin_time_square_kp20_kd0.6",
    "200g_35_v3_200g_r03_lift_and_drop_kp20_kd0.8",
    "500g_06_v3_500g_r01_sin_sin_kp20_kd1.2",
)
FIXTURES = {
    "examples/offline/README.md",
    "examples/offline/manifest.json",
    "examples/offline/model.json",
    "tests/fixtures/release/events.json",
    "tests/fixtures/release/scene.xml",
    *(f"examples/offline/raw/{record}/raw.json" for record in RECORDS),
    *(f"examples/offline/processed/{record}.json" for record in RECORDS),
    *(f"examples/offline/reference/{record}.npz" for record in RECORDS),
    *(
        f"tests/fixtures/release/{case}.npz"
        for case in ("processed_enable", "stop_tx", "stop_ack1", "stop_ack2")
    ),
    *(
        f"docs/images/{name}.png"
        for name in ("overview", "identification", "identification-dark", "bench-preview")
    ),
}
SKILLS = ("motorfit-setup", "motorfit-record", "motorfit-identify", "motorfit-validate")
SKILL_FILES = {f".agents/skills/{name}/SKILL.md" for name in SKILLS}
LINKS = {".claude/skills": "../.agents/skills"}
FORBIDDEN_PARTS = {
    "__pycache__",
    ".venv",
    ".venvs",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".superpowers",
    ".tox",
    ".nox",
    "node_modules",
    "wandb",
    "build",
    "dist",
    ".doctrees",
}
FORBIDDEN_PREFIXES = (
    "configs/local/",
    "configs/simulation/release/",
    "docs/images/references/",
    "docs/_build/",
)
FORBIDDEN_FILES = {"docs/images/overview-prompt.md", "docs/images/offline-replay.png"}


def git(*args, input=None):
    return subprocess.run(["git", *args], input=input, check=True, capture_output=True).stdout


def allowed(path):
    parts = PurePosixPath(path).parts
    if (
        set(parts) & FORBIDDEN_PARTS
        or path.startswith(FORBIDDEN_PREFIXES)
        or path in FORBIDDEN_FILES
        or any(p == ".env" or p.startswith(".env.") for p in parts)
    ):
        return False
    if path in ROOT_FILES | FIXTURES | SKILL_FILES | LINKS.keys() or path == "third_party/bam":
        return True
    return PurePosixPath(path).suffix in SOURCE_SUFFIXES.get(parts[0], set())


def main():
    errors, blobs = [], []
    entries = git("ls-files", "--stage", "-z").split(b"\0")
    for entry in filter(None, entries):
        metadata, raw_path = entry.split(b"\t", 1)
        mode, oid, stage = metadata.decode().split()
        path = raw_path.decode()
        if stage != "0":
            errors.append(f"{path}: unresolved index entry")
        if not allowed(path):
            errors.append(f"{path}: outside the tracked source/fixture allowlist")
        if path == "third_party/bam":
            if mode != "160000":
                errors.append(f"{path}: must remain a pinned Git submodule")
            continue
        if path in LINKS:
            if mode != "120000" or git("cat-file", "blob", oid).decode() != LINKS[path]:
                errors.append(f"{path}: expected relative skill discovery symlink")
        elif mode not in {"100644", "100755"}:
            errors.append(f"{path}: unexpected file mode {mode}")
        blobs.append((path, oid))

    ignored = git("ls-files", "--cached", "--ignored", "--exclude-standard", "-z")
    errors.extend(
        f"{p.decode()}: tracked despite an ignore rule" for p in ignored.split(b"\0") if p
    )
    total = 0
    if blobs:
        sizes = git(
            "cat-file",
            "--batch-check=%(objectsize)",
            input="".join(f"{oid}\n" for _, oid in blobs).encode(),
        ).splitlines()
        for (path, _), raw_size in zip(blobs, sizes, strict=True):
            size = int(raw_size)
            total += size
            if size > 5 * 1024 * 1024:
                errors.append(f"{path}: blob exceeds 5 MiB")
    if total > 20 * 1024 * 1024:
        errors.append("Tracked blobs exceed the 20 MiB source-and-example budget")
    if errors:
        print("Repository policy failed:\n- " + "\n- ".join(errors), file=sys.stderr)
        print(
            "Keep experiments in data/<study>/ and generated work in outputs/. "
            "See docs/repository.md.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Repository policy passed: {len(blobs)} files, {total / 1024**2:.2f} MiB; "
        "BAM is tracked separately as a submodule."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

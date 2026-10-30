"""Publish main or a release tag, preserving previously published documentation."""

import argparse
import html
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path

SITE_REPOSITORY = "git@github.com:motorfit/motorfit.github.io.git"
RELEASE = re.compile(r"v(\d+)\.(\d+)\.(\d+)\Z")


def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def redirect(path, target):
    path.parent.mkdir(parents=True, exist_ok=True)
    escaped = html.escape(target, quote=True)
    path.write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>MotorFit documentation</title>"
        f'<meta http-equiv="refresh" content="0; url={escaped}">'
        f'<link rel="canonical" href="{escaped}">'
        f"<script>location.replace({json.dumps(target)} + location.search + location.hash);</script>"
        f'<a href="{escaped}">Open MotorFit documentation</a></html>\n'
    )


def update_site(site, built, version, revision):
    target = site / version
    if version != "main" and target.exists():
        raise ValueError(f"{version} is already published; release documentation is immutable")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(built, target)
    (target / "versions.json").unlink()
    (target / ".buildinfo").unlink(missing_ok=True)
    (target / "source.json").write_text(json.dumps({"ref": version, "commit": revision}) + "\n")

    # Only directories produced by this publisher are documentation versions.
    releases = sorted(
        (
            p.name
            for p in site.iterdir()
            if RELEASE.fullmatch(p.name) and (p / "source.json").is_file()
        ),
        key=lambda name: tuple(map(int, RELEASE.fullmatch(name).groups())),
        reverse=True,
    )
    versions = [{"version": name, "url": f"/{name}/"} for name in releases]
    if versions:
        versions[0].update(name=f"{releases[0]} (stable)", preferred=True)
    if (site / "main/index.html").is_file():
        versions.append({"name": "main (dev)", "version": "main", "url": "/main/"})
    (site / "versions.json").write_text(json.dumps(versions, indent=2) + "\n")
    (site / ".nojekyll").touch()

    # Root bookmarks continue to track main, including moved-page redirects.
    if version == "main":
        protected = {".git", ".nojekyll", "CNAME", "versions.json", "main", *releases}
        old_pages = []
        for child in site.iterdir():
            if child.name in protected:
                continue
            if child.is_dir():
                if not child.name.startswith("_"):
                    old_pages.extend(p.relative_to(site) for p in child.rglob("*.html"))
                shutil.rmtree(child)
            else:
                if child.suffix == ".html":
                    old_pages.append(child.relative_to(site))
                child.unlink()
        pages = {
            p.relative_to(target)
            for p in target.rglob("*.html")
            if not p.relative_to(target).parts[0].startswith("_")
        }
        for page in pages | set(old_pages):
            destination = page.as_posix() if page in pages else "index.html"
            redirect(site / page, f"/main/{destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", default="main", help="main or a vX.Y.Z Git tag")
    parser.add_argument("--output", type=Path, help="prepare a local site without pushing")
    args = parser.parse_args()
    version = args.version
    if version != "main" and not RELEASE.fullmatch(version):
        parser.error("version must be main or a vX.Y.Z release tag")
    root = Path(git("rev-parse", "--show-toplevel"))
    if git(
        "status",
        "--porcelain",
        "--",
        "docs",
        "pyproject.toml",
        "uv.lock",
        "scripts/publish_docs.sh",
        "scripts/publish_docs.py",
        cwd=root,
    ):
        parser.error("Commit documentation inputs before publishing")
    ref = "refs/heads/main" if version == "main" else f"refs/tags/{version}"
    revision = git("rev-parse", f"{ref}^{{commit}}", cwd=root)
    with tempfile.TemporaryDirectory(prefix="motorfit-docs-") as temporary:
        temporary = Path(temporary)
        source = temporary / "source"
        source.mkdir()
        archive = subprocess.check_output(
            ["git", "archive", revision, "docs", "pyproject.toml", "uv.lock"], cwd=root
        )
        with tarfile.open(fileobj=io.BytesIO(archive)) as files:
            files.extractall(source, filter="data")
        package_version = tomllib.loads((source / "pyproject.toml").read_text())["project"][
            "version"
        ]
        if version != "main" and version != f"v{package_version}":
            parser.error("Release tag must match pyproject.toml version at that tag")
        built = temporary / "html"
        subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "--only-group",
                "docs",
                "sphinx-build",
                "-W",
                "--keep-going",
                "-b",
                "html",
                "-d",
                str(temporary / "doctrees"),
                "docs",
                str(built),
            ],
            cwd=source,
            env={
                **os.environ,
                "UV_PROJECT_ENVIRONMENT": str(temporary / "env"),
                "MOTORFIT_DOCS_VERSION": version,
            },
            check=True,
        )
        if args.output:
            site = args.output.resolve()
            if site.exists() and not (site / "versions.json").is_file():
                parser.error("--output must be new or an existing versioned documentation preview")
            if (site / ".git").exists():
                parser.error("--output cannot be a Git checkout")
            site.mkdir(parents=True, exist_ok=True)
        else:
            site = temporary / "site"
            subprocess.run(
                ["git", "clone", "--quiet", "--depth", "1", SITE_REPOSITORY, str(site)], check=True
            )
        update_site(site, built, version, revision)
        if args.output:
            print(f"Prepared {site}; serve this directory with python3 -m http.server")
            return
        git("add", "--all", cwd=site)
        if not git("diff", "--cached", "--stat", cwd=site):
            print("Published documentation already matches this build")
            return
        git(
            "commit",
            "--quiet",
            "-m",
            f"Publish {version} documentation from {revision[:12]}",
            cwd=site,
        )
        subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=site, check=True)
        print(f"Published https://motorfit.github.io/{version}/; GitHub Pages deployment follows")


if __name__ == "__main__":
    main()

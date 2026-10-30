#!/usr/bin/env bash
# Publish only a fresh Sphinx build; existing site history is retained.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
if [[ -n "$(git status --porcelain -- docs pyproject.toml uv.lock scripts/publish_docs.sh)" ]]; then
  echo "Commit documentation inputs before publishing." >&2
  exit 1
fi
source_revision="$(git rev-parse --short HEAD)"
publish_tmp="$(mktemp -d -t motorfit-docs.XXXXXXXX)"
trap 'rm -rf "$publish_tmp"' EXIT

UV_PROJECT_ENVIRONMENT="$publish_tmp/env" uv run --frozen --only-group docs sphinx-build \
  -W --keep-going -b html -d "$publish_tmp/doctrees" docs "$publish_tmp/html"
rm -f "$publish_tmp/html/.buildinfo"
git clone --quiet --depth 1 git@github.com:motorfit/motorfit.github.io.git "$publish_tmp/site"
git -C "$publish_tmp/site" checkout --quiet -B main

# The Git directory is outside the HTML tree, so no stale site files survive.
site_git=(git --git-dir="$publish_tmp/site/.git" --work-tree="$publish_tmp/html")
"${site_git[@]}" add --all
if "${site_git[@]}" diff --cached --quiet; then
  echo "The published documentation already matches this build."
  exit 0
fi
"${site_git[@]}" commit --quiet -m "Publish documentation from $source_revision"
"${site_git[@]}" push origin HEAD:main
echo "Published https://motorfit.github.io/ (source $source_revision); GitHub Pages deployment follows."

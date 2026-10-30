#!/usr/bin/env bash
# Keep the documented shell entry point; versioned publication uses Python's stdlib.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
exec python3 "$repo_root/scripts/publish_docs.py" "$@"

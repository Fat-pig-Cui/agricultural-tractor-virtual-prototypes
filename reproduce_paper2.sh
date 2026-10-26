#!/usr/bin/env bash
set -euo pipefail
archive_root="$(cd "$(dirname "$0")" && pwd)"
cd "$archive_root"
python3 tools/run_current_experiments.py paper2 "$@"

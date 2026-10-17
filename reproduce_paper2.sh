#!/usr/bin/env bash
set -euo pipefail

archive_root="$(cd "$(dirname "$0")" && pwd)"
cd "$archive_root"

python3 tools/run_paper2_major_revision.py
python3 tools/run_paper2_submitted_ablation.py
python3 tools/check_paper2_revision_physics.py
python3 tools/check_paper2_revision_execution.py
python3 tools/plot_paper2_major_revision.py

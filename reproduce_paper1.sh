#!/usr/bin/env bash
set -euo pipefail

archive_root="$(cd "$(dirname "$0")" && pwd)"
cd "$archive_root"

python3 tools/materialize_release_data.py
python3 tools/run_paper1_major_revision.py
python3 tools/extend_paper1_revision_audits.py
python3 tools/refine_paper1_comparators.py
python3 tools/replay_paper1_original_noise.py
python3 tools/rerun_paper1_mechanical_audit.py
python3 tools/run_paper1_rk4_convergence_audit.py
python3 tools/run_paper1_strengthening_audit.py
python3 tools/plot_paper1_major_revision.py

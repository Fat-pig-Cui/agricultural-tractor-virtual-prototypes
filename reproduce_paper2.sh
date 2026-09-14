#!/usr/bin/env bash
set -euo pipefail

archive_root="$(cd "$(dirname "$0")" && pwd)"
cd "$archive_root"

python3 tools/run_paper2_controller_framework_benchmark.py
python3 tools/plot_paper2_controller_framework.py
python3 tools/run_paper2_mpc_mechanism_map.py
python3 tools/plot_paper2_mpc_mechanism_map.py
python3 tools/run_paper2_ideal_oracle_envelope.py
python3 tools/draw_diagrams.py

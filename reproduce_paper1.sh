#!/usr/bin/env bash
set -euo pipefail

archive_root="$(cd "$(dirname "$0")" && pwd)"
cd "$archive_root"

python3 tools/run_paper1_statistics.py
python3 tools/run_lift_hold_validation.py
python3 tools/run_lift_ablation.py
python3 tools/run_lift_dual_gate_20seeds.py
python3 tools/run_lift_theoretical_stress.py
python3 tools/run_lift_submission_robustness.py
python3 tools/run_lift_steady_accuracy_scan.py
python3 tools/run_lift_fine_trim_scan.py
python3 tools/run_lift_combined_stress.py
python3 tools/run_paper1_measurement_observer_audit.py
python3 tools/export_paper1_traceability.py --check
python3 tools/draw_diagrams.py
python3 tools/plot_paper1_figures.py
python3 tools/plot_lift_combined_stress.py

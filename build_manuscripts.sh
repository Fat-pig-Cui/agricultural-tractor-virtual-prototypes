#!/usr/bin/env bash
set -euo pipefail

archive_root="$(cd "$(dirname "$0")" && pwd)"
cd "$archive_root/MDPI_template_ACS"

for manuscript in paper1_hitch_control_mdpi.tex paper2_energy_management_mdpi.tex; do
  xelatex -interaction=nonstopmode -halt-on-error "$manuscript"
  xelatex -interaction=nonstopmode -halt-on-error "$manuscript"
done

#!/usr/bin/env bash
set -euo pipefail

archive_root="$(cd "$(dirname "$0")" && pwd)"
cd "$archive_root/MDPI_template_ACS"

latex_compiler="${LATEX_COMPILER:-pdflatex}"

for manuscript in paper1_hitch_control_machines.tex paper2_energy_management_energies.tex; do
  "$latex_compiler" -interaction=nonstopmode -halt-on-error "$manuscript"
  "$latex_compiler" -interaction=nonstopmode -halt-on-error "$manuscript"
done

#!/usr/bin/env bash
set -euo pipefail

archive_root="$(cd "$(dirname "$0")" && pwd)"
latex_compiler="${LATEX_COMPILER:-pdflatex}"
for folder in machines_major_revision energies_major_revision; do
  cd "$archive_root/revisions/$folder"
  supplement="supplement"
  if [[ "$folder" == "machines_major_revision" ]]; then supplement="supplementary"; fi
  for manuscript in manuscript "$supplement"; do
    for iteration in 1 2 3; do
      "$latex_compiler" -interaction=nonstopmode -halt-on-error "$manuscript.tex"
    done
  done
done

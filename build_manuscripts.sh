#!/usr/bin/env bash
set -euo pipefail
archive_root="$(cd "$(dirname "$0")" && pwd)"
latex_compiler="${LATEX_COMPILER:-pdflatex}"
for paper in paper1 paper2; do
  cd "$archive_root/manuscripts/$paper"
  for document in manuscript supplementary; do
    for iteration in 1 2 3; do
      "$latex_compiler" -interaction=nonstopmode -halt-on-error "$document.tex"
    done
  done
done

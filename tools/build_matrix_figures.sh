#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
PDFLATEX_BIN="${PDFLATEX_BIN:-pdflatex}"
BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/scan2bim-matrix-figures.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT

if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="python3"
fi

"$PYTHON_BIN" tools/create_matrix_thesis_figures.py \
    --current data/10_runs/matrix_rest \
    --previous data/10_runs/matrix_full_pipe \
    --sugar-followup data/10_runs/matrix_sugar_followup_12 \
    --output-dir docs/grafiken/verwendet_verbessert

for source in docs/grafiken/verwendet_verbessert/matrix_*.tex; do
    name="$(basename "${source%.tex}")"
    "$PDFLATEX_BIN" \
        -interaction=nonstopmode \
        -halt-on-error \
        -output-directory="$BUILD_DIR" \
        "$source" >/dev/null
    cp "$BUILD_DIR/$name.pdf" "docs/grafiken/verwendet_verbessert/$name.pdf"
done

echo "Matrix graphics written to $PROJECT_ROOT/docs/grafiken"

#!/usr/bin/env bash
set -euo pipefail

PA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PA_DIR"
mkdir -p build

latexmk -pdf \
  -jobname=pa_anonym \
  -interaction=nonstopmode \
  -halt-on-error \
  -outdir=build \
  main_anonym.tex

printf 'PDF erzeugt: %s\n' "$PA_DIR/build/pa_anonym.pdf"

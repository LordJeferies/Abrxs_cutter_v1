#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/tools/lib/python_resolver.zsh"
[[ -n "$ABRXOS_PYTHON" ]] || { echo "ERROR: Python no encontrado"; exit 2; }
"$ABRXOS_PYTHON" "$ROOT/tools/GENERAR_MANIFEST.py"

#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/tools/lib/python_resolver.zsh"
[[ -n "$ABRXOS_PYTHON" ]] || { echo "ERROR: Python >=3.11 no encontrado."; exit 2; }

candidates=(
  "$HOME/ABRXOS_CUTTER_APP"
  "$HOME/ABRXOS_MULTI_CUTTER"
)
source_dir="${1:-}"
for c in "${candidates[@]}"; do
  [[ -n "$source_dir" ]] && break
  if [[ -d "$c" ]]; then
    if [[ -f "$c/ABRXOS_CUTTER_CONTROL_PANEL_V3.py" || -f "$c/ABRXOS_CUTTER_CONTROL_PANEL.py" ]]; then source_dir="$c"; break; fi
    [[ -z "$source_dir" ]] && source_dir="$c"
  fi
done
if [[ -z "$source_dir" ]]; then
  echo "No encontré Cutter en rutas conocidas."
  echo "Arrastra la carpeta fuente del Cutter y presiona Enter:"
  read "source_dir?> "
  source_dir="${source_dir%\'}"; source_dir="${source_dir#\'}"; source_dir="${source_dir%\"}"; source_dir="${source_dir#\"}"
fi
[[ -d "$source_dir" ]] || { echo "ERROR: source inválido: $source_dir"; exit 3; }

mkdir -p "$ROOT/apps/cutter"
"$ABRXOS_PYTHON" "$ROOT/tools/capture_cutter.py" \
  --source "$source_dir" \
  --dest "$ROOT/apps/cutter/current" \
  --metadata-out "$ROOT/CURRENT_CUTTER.json" \
  --requirements-out "$ROOT/requirements-runtime.txt" \
  --models-out "$ROOT/models/MODELS_MANIFEST.json"

echo "Cutter capturado desde: $source_dir"

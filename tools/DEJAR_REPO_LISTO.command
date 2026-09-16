#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
/bin/zsh "$ROOT/tools/CAPTURAR_CUTTER_ACTUAL.command" "${1:-}"
/bin/zsh "$ROOT/tools/VERIFY_ALL.command"
/bin/zsh "$ROOT/tools/GENERAR_MANIFEST.command"
echo "REPO CUTTER LISTO PARA PREPARAR GITHUB."
echo "Siguiente: zsh \"$ROOT/tools/PREPARAR_REPO_GITHUB.command\""

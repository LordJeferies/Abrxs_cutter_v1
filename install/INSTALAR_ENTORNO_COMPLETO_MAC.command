#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "ABRXS CUTTER · SETUP COMPLETO MAC"
echo "================================="
/bin/zsh "$ROOT/install/INSTALAR_DEPENDENCIAS_MAC.command" "$@"
/bin/zsh "$ROOT/install/INSTALAR_MODELOS.command" "$@"
/bin/zsh "$ROOT/install/INSTALAR_CUTTER_DESDE_CERO.command"
echo
echo "SETUP COMPLETO. Abre desde Desktop: ABRXOS Cutter.app"

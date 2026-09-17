#!/bin/zsh
set -euo pipefail

export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
PY="$HOME/.abrxos/cutter/venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"
TOOL="$HOME/ABRXOS_CUTTER_APP/ABRXOS_CUTTER_PROCESS_CONTROL_V311.py"

if [[ ! -f "$TOOL" ]]; then
  echo "ERROR: Process Control 3.1.1 no está instalado todavía."
  echo "Ruta esperada: $TOOL"
  read "_?Pulsa Enter para cerrar..."
  exit 2
fi

show_status() {
  echo
  echo "=== ESTADO CUTTER ==="
  "$PY" "$TOOL" probe --json | "$PY" -m json.tool
}

cancel_renders() {
  show_status
  echo
  read "choice?Escribe CANCELAR para detener todos los renders Cutter activos: "
  if [[ "$choice" == "CANCELAR" ]]; then
    "$PY" "$TOOL" cancel --all --json | "$PY" -m json.tool
  else
    echo "No se canceló nada."
  fi
}

while true; do
  clear
  echo "ABRXS Cutter 3.1.1 · Process Control"
  echo "====================================="
  echo "1) Ver procesos"
  echo "2) Cancelar renders"
  echo "3) Cerrar panel Cutter"
  echo "4) Salir"
  echo
  read "choice?Elige una opción: "
  case "$choice" in
    1) show_status; read "_?Pulsa Enter para continuar..." ;;
    2) cancel_renders; read "_?Pulsa Enter para continuar..." ;;
    3) "$PY" "$TOOL" stop-panel --all --json | "$PY" -m json.tool; read "_?Pulsa Enter para continuar..." ;;
    4) exit 0 ;;
    *) echo "Opción no válida"; sleep 1 ;;
  esac
done

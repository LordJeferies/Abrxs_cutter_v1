#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRY=0; YES=0
for arg in "$@"; do [[ "$arg" == "--dry-run" ]] && DRY=1; [[ "$arg" == "--yes" ]] && YES=1; done
source "$ROOT/tools/lib/python_resolver.zsh"

say(){ print -r -- "$@"; }
run(){ if [[ "$DRY" -eq 1 ]]; then say "DRY-RUN: $*"; else "$@"; fi }

say "ABRXS CUTTER · DEPENDENCIAS MAC"
say "================================"

if ! command -v brew >/dev/null 2>&1; then
  if [[ "$DRY" -eq 1 ]]; then
    say "DRY-RUN: instalar Homebrew desde https://brew.sh"
  else
    if [[ "$YES" -ne 1 ]]; then
      say "Homebrew falta y es necesario para un setup reproducible de FFmpeg/Python."
      read "ans?¿Instalar Homebrew oficial ahora? [y/N] "
      [[ "$ans" == [yY] ]] || { say "Cancelado sin modificar el sistema."; exit 2; }
    fi
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [[ -x /opt/homebrew/bin/brew ]]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
  fi
fi

if [[ -z "${ABRXOS_PYTHON:-}" ]]; then
  run brew install python@3.14
  source "$ROOT/tools/lib/python_resolver.zsh"
fi
say "Python: $ABRXOS_PYTHON"

if ! command -v brew >/dev/null 2>&1 && [[ "$DRY" -ne 1 ]]; then
  say "ERROR: Homebrew sigue sin estar disponible."
  exit 3
fi

command -v ffmpeg >/dev/null 2>&1 || run brew install ffmpeg
command -v ffprobe >/dev/null 2>&1 || run brew install ffmpeg
command -v git >/dev/null 2>&1 || run brew install git
command -v gh >/dev/null 2>&1 || say "NOTA: gh no es runtime; instala con 'brew install gh' sólo si quieres publicar desde Terminal."

VENV="$HOME/.abrxos/cutter/venv"
if [[ "$DRY" -eq 1 ]]; then
  say "DRY-RUN: $ABRXOS_PYTHON -m venv $VENV"
else
  "$ABRXOS_PYTHON" -m venv "$VENV"
fi
VPY="$VENV/bin/python3"
if [[ "$DRY" -eq 0 ]]; then
  "$VPY" -m pip install --upgrade pip
  if grep -vE '^\s*(#|$)' "$ROOT/requirements-runtime.txt" >/tmp/abrxs_cutter_requirements.$$ 2>/dev/null; then
    "$VPY" -m pip install -r /tmp/abrxs_cutter_requirements.$$
  fi
  rm -f /tmp/abrxs_cutter_requirements.$$ 2>/dev/null || true
fi

if command -v ffmpeg >/dev/null 2>&1; then
  if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox; then
    say "✓ h264_videotoolbox disponible"
  else
    say "ADVERTENCIA: FFmpeg no reporta h264_videotoolbox."
  fi
fi
say "Dependencias base preparadas. Venv: $VENV"

#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/tools/lib/python_resolver.zsh"
echo "ABRXS CUTTER · PREFLIGHT"
echo "Python: ${ABRXOS_PYTHON:-MISSING}"
echo "ffmpeg: $(command -v ffmpeg || echo MISSING)"
echo "ffprobe: $(command -v ffprobe || echo MISSING)"
echo "git: $(command -v git || echo MISSING)"
echo "gh: $(command -v gh || echo OPTIONAL_MISSING)"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -hide_banner -encoders 2>/dev/null | grep h264_videotoolbox || true
fi
[[ -f "$ROOT/CURRENT_CUTTER.json" ]] && cat "$ROOT/CURRENT_CUTTER.json" || echo "CURRENT_CUTTER.json pendiente de captura"

#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/apps/cutter/current"
META="$ROOT/CURRENT_CUTTER.json"
DEST="$HOME/ABRXOS_CUTTER_APP"
APP="$HOME/Desktop/ABRXOS Cutter.app"
FALLBACK="$HOME/Desktop/ABRXOS Cutter.command"
LOG="$HOME/Library/Logs/abrxos_cutter.log"

[[ -f "$META" && -d "$SRC" ]] || { echo "ERROR: repo aún no capturó Cutter actual. Ejecuta tools/CAPTURAR_CUTTER_ACTUAL.command en la Mac fuente y haz commit."; exit 2; }
/bin/zsh "$ROOT/install/INSTALAR_DEPENDENCIAS_MAC.command"
source "$ROOT/tools/lib/python_resolver.zsh"
VENV_PY="$HOME/.abrxos/cutter/venv/bin/python3"
[[ -x "$VENV_PY" ]] || VENV_PY="$ABRXOS_PYTHON"
ENTRY="$($ABRXOS_PYTHON - "$META" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['entrypoint'])
PY
)"
[[ -f "$SRC/$ENTRY" ]] || { echo "ERROR: entrypoint no existe: $SRC/$ENTRY"; exit 3; }
mkdir -p "$DEST" "$HOME/Library/Logs" "$HOME/Desktop"
rsync -a --delete --exclude '.git' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '*.pyc' "$SRC/" "$DEST/"
LAUNCH="$DEST/LAUNCH_ABRXOS_CUTTER.command"
cat > "$LAUNCH" <<EOF
#!/bin/zsh
mkdir -p "$HOME/Library/Logs"
nohup "$VENV_PY" "$DEST/$ENTRY" >> "$LOG" 2>&1 &
exit 0
EOF
chmod +x "$LAUNCH"
rm -rf "$APP"
if command -v osacompile >/dev/null 2>&1; then
  osacompile -o "$APP" -e "do shell script \"/bin/zsh \" & quoted form of \"$LAUNCH\"" >/dev/null
else
  cp "$LAUNCH" "$FALLBACK"; chmod +x "$FALLBACK"
fi

echo "✓ Cutter instalado: $DEST"
echo "✓ Launcher: $APP"
echo "✓ Python runtime: $VENV_PY"
echo "✓ FFmpeg: $(command -v ffmpeg || true)"

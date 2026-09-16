#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
YES=0; DRY=0
for arg in "$@"; do [[ "$arg" == "--yes" ]] && YES=1; [[ "$arg" == "--dry-run" ]] && DRY=1; done
VENV="$HOME/.abrxos/cutter/venv"
VPY="$VENV/bin/python3"
[[ -x "$VPY" ]] || { echo "Primero ejecuta install/INSTALAR_DEPENDENCIAS_MAC.command"; exit 2; }
COUNT="$($VPY - "$ROOT/models/MODELS_MANIFEST.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))
print(len([x for x in m.get('models',[]) if x.get('required',True)]))
PY
)"
if [[ "$COUNT" -eq 0 ]]; then
  echo "No hay modelos requeridos declarados por el Cutter actual."
  exit 0
fi

echo "Modelos requeridos declarados: $COUNT"
if [[ "$DRY" -eq 1 ]]; then
  "$VPY" - "$ROOT/models/MODELS_MANIFEST.json" <<'PY'
import json,sys
for x in json.load(open(sys.argv[1])).get('models',[]):
    if x.get('required',True): print('DRY-RUN:',x.get('id'))
PY
  exit 0
fi
if [[ "$YES" -ne 1 ]]; then
  echo "La descarga puede ocupar varios GB según el modelo."
  read "ans?¿Pre-descargar ahora todos los modelos requeridos? [y/N] "
  [[ "$ans" == [yY] ]] || { echo "Omitido. Los frameworks podrán descargarlos on-demand."; exit 0; }
fi
"$VPY" -m pip install --upgrade huggingface_hub
"$VPY" - "$ROOT/models/MODELS_MANIFEST.json" <<'PY'
import json,sys
from huggingface_hub import snapshot_download
manifest=json.load(open(sys.argv[1]))
for x in manifest.get('models',[]):
    if not x.get('required',True): continue
    repo=x.get('id')
    if not repo: continue
    print('Descargando modelo:',repo,flush=True)
    path=snapshot_download(repo_id=repo)
    print('✓',repo,'->',path)
PY

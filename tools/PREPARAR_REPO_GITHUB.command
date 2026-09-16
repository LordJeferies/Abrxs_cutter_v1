#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "ABRXS CUTTER · PREPARAR GITHUB"
echo "==============================="
/bin/zsh "$ROOT/tools/VERIFY_ALL.command"
/bin/zsh "$ROOT/tools/GENERAR_MANIFEST.command"
if [[ ! -d "$ROOT/.git" ]]; then git -C "$ROOT" init -b main; fi
TOP="$(git -C "$ROOT" rev-parse --show-toplevel)"
[[ "$TOP" == "$ROOT" ]] || { echo "ERROR: git root=$TOP; esperado=$ROOT"; exit 20; }
git -C "$ROOT" add -A
cat > "$ROOT/GITHUB_NEXT_STEPS.txt" <<'EOF'
REPO OFICIAL: Abrxs_cutter_v1

1. git status
2. git diff --cached
3. git commit -m "Abrxs_cutter_v1 · reproducible current snapshot"
4. gh repo create Abrxs_cutter_v1 --private --source=. --remote=origin --push
5. git tag abrxs-cutter-v1.0.0
6. git push origin --tags
EOF
echo "Preparado. Repo GitHub objetivo: Abrxs_cutter_v1"

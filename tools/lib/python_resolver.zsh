#!/bin/zsh
set -euo pipefail
resolve_python(){
  local c
  for c in \
    "${ABRXOS_PYTHON:-}" \
    "$(command -v python3 2>/dev/null || true)" \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /usr/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/*/bin/python3
  do
    [[ -n "$c" && -x "$c" ]] || continue
    "$c" - <<'PY' >/dev/null 2>&1 || continue
import sys
raise SystemExit(0 if sys.version_info >= (3,11) else 1)
PY
    print -r -- "$c"
    return 0
  done
  return 1
}
ABRXOS_PYTHON="$(resolve_python || true)"
export ABRXOS_PYTHON

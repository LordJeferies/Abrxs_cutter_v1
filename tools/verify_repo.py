#!/usr/bin/env python3
from __future__ import annotations
import json, hashlib, subprocess, sys, shutil, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
errors=[];warnings=[];checks=[]
meta_path=ROOT/'CURRENT_CUTTER.json'; src=ROOT/'apps/cutter/current'
if not meta_path.exists(): errors.append('CURRENT_CUTTER.json missing; run tools/CAPTURAR_CUTTER_ACTUAL.command')
else:
    try: meta=json.loads(meta_path.read_text())
    except Exception as e: errors.append(f'invalid CURRENT_CUTTER.json: {e}');meta={}
    entry=meta.get('entrypoint')
    if not entry or not (src/entry).is_file(): errors.append(f'entrypoint missing: {entry}')
    else: checks.append('entrypoint=PASS')
for p in src.rglob('*') if src.exists() else []:
    if p.is_file() and (p.name.startswith('LAUNCH_') or p.suffix in {'.pyc','.pyo'}): errors.append(f'generated artifact in snapshot: {p.relative_to(ROOT)}')
    if p.is_file() and p.suffix.lower() not in {'.png','.jpg','.jpeg','.mov','.mp4','.zip'}:
        try:t=p.read_text(encoding='utf-8',errors='ignore')
        except Exception:continue
        if re.search(r'/Users/[^/]+/',t): errors.append(f'machine-specific path in {p.relative_to(ROOT)}')
for p in src.rglob('*.py') if src.exists() else []:
    try: compile(p.read_text(encoding='utf-8'),str(p),'exec')
    except Exception as e: errors.append(f'python syntax: {p.relative_to(ROOT)}: {e}')
checks.append('python_compile=PASS' if not [e for e in errors if e.startswith('python syntax:')] else 'python_compile=FAIL')
ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
if ffmpeg and ffprobe:
    checks.append('ffmpeg=PASS');checks.append('ffprobe=PASS')
    r=subprocess.run([ffmpeg,'-hide_banner','-encoders'],capture_output=True,text=True)
    if 'h264_videotoolbox' in (r.stdout+r.stderr):checks.append('h264_videotoolbox=PASS')
    else:warnings.append('ffmpeg present but h264_videotoolbox not detected')
else:warnings.append('ffmpeg/ffprobe missing on this machine; run install/INSTALAR_DEPENDENCIAS_MAC.command')
req=ROOT/'requirements-runtime.txt'
if req.exists(): checks.append('requirements_manifest=PASS')
else: errors.append('requirements-runtime.txt missing')
models=ROOT/'models/MODELS_MANIFEST.json'
if models.exists():
    try:json.loads(models.read_text());checks.append('models_manifest=PASS')
    except Exception as e:errors.append(f'invalid models manifest: {e}')
else:errors.append('models manifest missing')
report={'schemaVersion':'abrxs.cutter.repo-verify.v1','ok':not errors,'errors':errors,'warnings':warnings,'checks':checks}
(ROOT/'LOCAL_VERIFY_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)

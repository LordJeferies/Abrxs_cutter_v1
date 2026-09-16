#!/usr/bin/env python3
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
exclude={'.git','.pytest_cache','__pycache__'}
rows=[]
for p in sorted(ROOT.rglob('*')):
    if not p.is_file() or any(x in p.parts for x in exclude) or p.name in {'REPO_MANIFEST.json','MANIFEST_SHA256.txt'}:continue
    h=hashlib.sha256(p.read_bytes()).hexdigest();rows.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':h})
(ROOT/'REPO_MANIFEST.json').write_text(json.dumps({'schemaVersion':'abrxs.cutter.repo-manifest.v1','files':rows},indent=2)+'\n')
(ROOT/'MANIFEST_SHA256.txt').write_text('\n'.join(f"{r['sha256']}  {r['path']}" for r in rows)+'\n')
print(json.dumps({'ok':True,'files':len(rows)},indent=2))

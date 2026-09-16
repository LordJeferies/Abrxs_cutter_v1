#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, json, re, shutil, sys, sysconfig
from pathlib import Path

ENTRYPOINT_PRIORITY=(
    'ABRXOS_CUTTER_CONTROL_PANEL_V3.py',
    'ABRXOS_CUTTER_CONTROL_PANEL.py',
    'ABRXOS_MULTI_HTML_CUTTER_V2.py',
    'ABRXOS_MULTI_HTML_CUTTER.py',
    'app.py','cutter.py','main.py'
)
EXCLUDE_DIRS={'.git','__pycache__','.pytest_cache','outputs','output','exports','renders','cache','.cache','media','videos'}
EXCLUDE_SUFFIXES={'.pyc','.pyo','.log','.tmp','.mov','.mp4','.mkv','.avi','.m4v'}
PIP_MAP={
    'requests':'requests','numpy':'numpy','PIL':'pillow','cv2':'opencv-python',
    'flask':'flask','fastapi':'fastapi','uvicorn':'uvicorn','tqdm':'tqdm',
    'mlx':'mlx','mlx_whisper':'mlx-whisper','whisper':'openai-whisper','torch':'torch',
    'pydantic':'pydantic','watchdog':'watchdog','aiofiles':'aiofiles'
}
MODEL_RE=re.compile(r"(?:mlx-community|openai|Systran|distil-whisper)/[A-Za-z0-9._-]+")

def version_of(src: Path)->str:
    vf=src/'VERSION.json'
    if vf.exists():
        try:
            v=json.loads(vf.read_text(encoding='utf-8')).get('version')
            if v:return str(v)
        except Exception:pass
    for p in src.glob('*.py'):
        m=re.search(r'V(\d+(?:\.\d+){0,3})',p.name,re.I)
        if m:return m.group(1)
    return 'captured-unknown'

def entrypoint_of(src: Path)->str:
    for name in ENTRYPOINT_PRIORITY:
        if (src/name).is_file():return name
    py=sorted(p.name for p in src.glob('*.py') if not p.name.startswith('test_'))
    if len(py)==1:return py[0]
    if py:return py[0]
    raise SystemExit('No se encontró entrypoint Python en el Cutter seleccionado.')

def imports_and_models(src: Path):
    mods=set();models=set();files=[]
    for p in src.rglob('*.py'):
        if any(part in EXCLUDE_DIRS for part in p.parts):continue
        try:text=p.read_text(encoding='utf-8',errors='replace')
        except Exception:continue
        files.append(p)
        for model in MODEL_RE.findall(text):models.add(model)
        try:tree=ast.parse(text)
        except SyntaxError:continue
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for n in node.names:mods.add(n.name.split('.')[0])
            elif isinstance(node,ast.ImportFrom) and node.module:
                mods.add(node.module.split('.')[0])
    std=set(getattr(sys,'stdlib_module_names',set()))|{'__future__'}
    req=sorted({PIP_MAP[m] for m in mods if m not in std and m in PIP_MAP})
    return sorted(mods),req,sorted(models),files

def ignore(directory,names):
    out=[]
    for n in names:
        p=Path(directory)/n
        if n in EXCLUDE_DIRS or n.startswith('LAUNCH_') or n=='.DS_Store':out.append(n);continue
        if p.is_file() and p.suffix.lower() in EXCLUDE_SUFFIXES:out.append(n)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',required=True);ap.add_argument('--dest',required=True)
    ap.add_argument('--metadata-out',required=True);ap.add_argument('--requirements-out',required=True);ap.add_argument('--models-out',required=True)
    args=ap.parse_args();src=Path(args.source).expanduser().resolve();dest=Path(args.dest).expanduser().resolve()
    if not src.is_dir():raise SystemExit(f'No existe source: {src}')
    entry=entrypoint_of(src);version=version_of(src);mods,req,models,files=imports_and_models(src)
    if dest.exists():shutil.rmtree(dest)
    shutil.copytree(src,dest,ignore=ignore)
    meta={
        'schemaVersion':'abrxs.cutter.current.v1','product':'ABRXOS Cutter','version':version,'entrypoint':entry,
        'capturedFrom':str(src),'pythonModulesDetected':mods,'requirements':req,
        'externalToolsRequired':['ffmpeg','ffprobe'],'desktopAppName':'ABRXOS Cutter.app'
    }
    Path(args.metadata_out).write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    Path(args.requirements_out).write_text(('\n'.join(req)+'\n') if req else '# No external Python packages detected from current source.\n',encoding='utf-8')
    model_rows=[{'id':m,'provider':'huggingface','required':True,'installMode':'on_demand','notes':'Detected as literal reference in Cutter source.'} for m in models]
    mm={'schemaVersion':'abrxs.cutter.models.v1','models':model_rows,'policy':'Only download models declared by current Cutter source or explicitly added by maintainer.'}
    Path(args.models_out).write_text(json.dumps(mm,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':True,'source':str(src),'dest':str(dest),'entrypoint':entry,'version':version,'requirements':req,'models':models},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

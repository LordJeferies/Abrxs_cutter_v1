from pathlib import Path
import json, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parents[1]


def run_capture_helper(src: Path, out: Path):
    cmd=[sys.executable,str(ROOT/'tools/capture_cutter.py'),'--source',str(src),'--dest',str(out),'--metadata-out',str(out.parent/'CURRENT_CUTTER.json'),'--requirements-out',str(out.parent/'requirements-runtime.txt'),'--models-out',str(out.parent/'MODELS_MANIFEST.json')]
    return subprocess.run(cmd,capture_output=True,text=True)


def test_capture_detects_control_panel_entrypoint_and_known_requirements(tmp_path):
    src=tmp_path/'ABRXOS_CUTTER_APP';src.mkdir()
    (src/'ABRXOS_CUTTER_CONTROL_PANEL_V3.py').write_text('import requests\nimport numpy\nimport subprocess\n',encoding='utf-8')
    (src/'VERSION.json').write_text(json.dumps({'version':'3.0.0'}),encoding='utf-8')
    out=tmp_path/'repo'/'current';out.parent.mkdir()
    r=run_capture_helper(src,out)
    assert r.returncode==0,r.stderr
    meta=json.loads((out.parent/'CURRENT_CUTTER.json').read_text())
    assert meta['entrypoint']=='ABRXOS_CUTTER_CONTROL_PANEL_V3.py'
    assert meta['version']=='3.0.0'
    req=(out.parent/'requirements-runtime.txt').read_text().splitlines()
    assert 'requests' in req and 'numpy' in req
    assert not any('subprocess'==x for x in req)


def test_capture_excludes_machine_artifacts_outputs_and_launchers(tmp_path):
    src=tmp_path/'src';src.mkdir();(src/'main.py').write_text('print(1)')
    (src/'LAUNCH_LOCAL.command').write_text('/Users/someone/private/path')
    (src/'__pycache__').mkdir();(src/'__pycache__'/'x.pyc').write_bytes(b'x')
    (src/'outputs').mkdir();(src/'outputs'/'big.mp4').write_bytes(b'x')
    out=tmp_path/'repo'/'current';out.parent.mkdir()
    r=run_capture_helper(src,out);assert r.returncode==0,r.stderr
    assert not (out/'LAUNCH_LOCAL.command').exists()
    assert not (out/'__pycache__').exists()
    assert not (out/'outputs').exists()


def test_capture_detects_literal_model_reference(tmp_path):
    src=tmp_path/'src';src.mkdir()
    (src/'main.py').write_text("import mlx_whisper\nMODEL='mlx-community/whisper-large-v3-turbo'\n")
    out=tmp_path/'repo'/'current';out.parent.mkdir()
    r=run_capture_helper(src,out);assert r.returncode==0,r.stderr
    models=json.loads((out.parent/'MODELS_MANIFEST.json').read_text())
    assert any(m['id']=='mlx-community/whisper-large-v3-turbo' for m in models['models'])
    req=(out.parent/'requirements-runtime.txt').read_text()
    assert 'mlx-whisper' in req

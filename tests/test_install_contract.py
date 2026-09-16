from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]

def test_dependency_installer_has_dry_run_and_required_runtime_tools():
    p=ROOT/'install/INSTALAR_DEPENDENCIAS_MAC.command'; assert p.exists()
    s=p.read_text()
    assert '--dry-run' in s
    assert 'ffmpeg' in s and 'ffprobe' in s
    assert 'h264_videotoolbox' in s
    assert '.abrxos/cutter/venv' in s
    assert 'requirements-runtime.txt' in s

def test_from_zero_installer_uses_current_metadata_and_desktop_app():
    p=ROOT/'install/INSTALAR_CUTTER_DESDE_CERO.command'; assert p.exists()
    s=p.read_text()
    assert 'CURRENT_CUTTER.json' in s
    assert 'apps/cutter/current' in s
    assert 'ABRXOS Cutter.app' in s
    assert 'ABRXOS_CUTTER_APP' in s

def test_shell_scripts_parse_with_bash():
    for p in list((ROOT/'install').glob('*.command'))+list((ROOT/'tools').glob('*.command')):
        r=subprocess.run(['bash','-n',str(p)],capture_output=True,text=True)
        assert r.returncode==0,(p,r.stderr)

def test_github_prep_is_root_scoped_and_uses_cutter_repo_name():
    p=ROOT/'tools/PREPARAR_REPO_GITHUB.command'; assert p.exists()
    s=p.read_text()
    assert 'Abrxs_cutter_v1' in s
    assert 'git -C "$ROOT" init' in s
    assert 'rev-parse --show-toplevel' in s
    assert 'git add .' not in s


def test_verify_checks_snapshot_metadata_and_machine_paths():
    p=ROOT/'tools/verify_repo.py'; assert p.exists()
    s=p.read_text()
    assert 'CURRENT_CUTTER.json' in s
    assert "machine-specific" in s
    assert 'ffmpeg' in s

def test_full_environment_installer_exists_and_chains_dependencies_models_and_cutter():
    p=ROOT/'install/INSTALAR_ENTORNO_COMPLETO_MAC.command'; assert p.exists()
    s=p.read_text()
    assert 'INSTALAR_DEPENDENCIAS_MAC.command' in s
    assert 'INSTALAR_MODELOS.command' in s
    assert 'INSTALAR_CUTTER_DESDE_CERO.command' in s

def test_model_installer_can_prefetch_declared_huggingface_models_with_confirmation():
    p=ROOT/'install/INSTALAR_MODELOS.command'; assert p.exists()
    s=p.read_text()
    assert 'snapshot_download' in s
    assert '--yes' in s
    assert '--dry-run' in s
    assert 'huggingface_hub' in s

def test_capture_wrapper_accepts_explicit_source_argument():
    p=ROOT/'tools/CAPTURAR_CUTTER_ACTUAL.command'; s=p.read_text()
    assert '${1:-}' in s
    assert 'source_dir="${1:-}"' in s

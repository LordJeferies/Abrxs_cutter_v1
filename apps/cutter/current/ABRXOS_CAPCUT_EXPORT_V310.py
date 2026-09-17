#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ABRXS Cutter 3.1.0 · CapCut export layer.

Additive runtime layer for ABRXOS_MULTI_HTML_CUTTER_V2.
It preserves sourceRanges semantics and cache behavior while exposing the
already-rendered parts in a human-readable CapCut package.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

CAPCUT_LAYER_VERSION = "3.1.0"
ENGINE_TARGET_VERSION = "2.1.0"
OUTPUT_MODES = {"complete_only", "complete_and_sections", "sections_only"}
DEFAULT_NEW_SETUP_MODE = "complete_and_sections"
DEFAULT_LEGACY_MODE = "complete_only"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_output_mode(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if value in OUTPUT_MODES else DEFAULT_LEGACY_MODE


def wants_complete(mode: str) -> bool:
    return normalize_output_mode(mode) in {"complete_only", "complete_and_sections"}


def wants_sections(mode: str) -> bool:
    return normalize_output_mode(mode) in {"complete_and_sections", "sections_only"}


def _slug(value: str, fallback: str = "SEGMENTO", limit: int = 48) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.upper()
    value = re.sub(r"[^A-Z0-9]+", "_", value).strip("_")
    value = re.sub(r"_+", "_", value)
    return (value[:limit].rstrip("_") or fallback)


def _tc(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    sec -= h * 3600
    m = int(sec // 60)
    sec -= m * 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"


def section_filename(index: int, segment: Dict[str, Any]) -> str:
    role = _slug(str(segment.get("role") or ""), fallback="SEGMENTO")
    return f"{int(index):02d}__{role}.mp4"


def complete_filename(job: Dict[str, Any]) -> str:
    pid = _slug(str(job.get("piece_id") or "PIEZA"), fallback="PIEZA")
    ori = _slug(str(job.get("orientation") or "video"), fallback="VIDEO")
    return f"{pid}__COMPLETO__{ori}.mp4"


def package_root(output: Path, job: Dict[str, Any]) -> Path:
    return output.parent / "CAPCUT" / _slug(str(job.get("orientation") or "video"), fallback="VIDEO")


def build_package_manifest(
    job: Dict[str, Any],
    mode: str,
    section_files: Iterable[str],
    complete_file: Optional[str],
) -> Dict[str, Any]:
    names = list(section_files)
    segments = []
    for idx, seg in enumerate(job.get("segments") or [], 1):
        file_name = names[idx - 1] if idx - 1 < len(names) else None
        segments.append({
            "index": int(seg.get("index") or idx),
            "order": seg.get("order", idx),
            "sourceStart": float(seg.get("start", 0.0)),
            "sourceEnd": float(seg.get("end", 0.0)),
            "duration": float(seg.get("duration", float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))),
            "role": str(seg.get("role") or ""),
            "speaker": str(seg.get("speaker") or ""),
            "text": str(seg.get("text") or ""),
            "file": file_name,
        })
    return {
        "schemaVersion": "abrxos.capcut-package.v1",
        "cutterVersion": CAPCUT_LAYER_VERSION,
        "pieceId": str(job.get("piece_id") or ""),
        "title": str(job.get("title") or ""),
        "pieceType": str(job.get("piece_type") or ""),
        "orientation": str(job.get("orientation") or ""),
        "sourceCode": str(job.get("source_code") or ""),
        "mode": normalize_output_mode(mode),
        "completeFile": complete_file,
        "segments": segments,
        "generatedAt": now_iso(),
    }


def _link_or_copy(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        if tmp.exists():
            tmp.unlink()
        try:
            os.link(source, tmp)
        except OSError:
            shutil.copy2(source, tmp)
        os.replace(tmp, dest)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def export_capcut_package(
    output: Path,
    job: Dict[str, Any],
    mode: str,
    parts: List[Path],
) -> Dict[str, Any]:
    mode = normalize_output_mode(mode)
    root = package_root(Path(output), job)
    root.mkdir(parents=True, exist_ok=True)

    section_names: List[str] = []
    if wants_sections(mode):
        section_dir = root / "01_SECCIONES"
        section_dir.mkdir(parents=True, exist_ok=True)
        for idx, (seg, part) in enumerate(zip(job.get("segments") or [], parts), 1):
            name = section_filename(idx, seg)
            _link_or_copy(Path(part), section_dir / name)
            section_names.append(name)

        order_lines = [
            f"ABRXS Cutter {CAPCUT_LAYER_VERSION} · ORDEN CAPCUT",
            f"Pieza: {job.get('piece_id','')} · {job.get('title','')}",
            f"Orientación: {str(job.get('orientation','')).upper()}",
            "",
        ]
        for idx, seg in enumerate(job.get("segments") or [], 1):
            name = section_names[idx - 1]
            role = str(seg.get("role") or "SEGMENTO")
            text = str(seg.get("text") or "")
            order_lines.append(
                f"{idx:02d}. {name} | {_tc(seg.get('start',0))} → {_tc(seg.get('end',0))} | {role} | {text}"
            )
        _write_atomic(root / "ORDEN_CAPCUT.txt", "\n".join(order_lines).rstrip() + "\n")
    else:
        # Do not delete a prior sections package: non-destructive by design.
        section_names = []

    complete_name: Optional[str] = None
    if wants_complete(mode):
        if not Path(output).exists():
            raise FileNotFoundError(f"Video completo no encontrado: {output}")
        complete_name = complete_filename(job)
        _link_or_copy(Path(output), root / "02_COMPLETO" / complete_name)

    manifest = build_package_manifest(job, mode, section_names, complete_name)
    _write_atomic(root / "SECCIONES.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return {
        "ok": True,
        "mode": mode,
        "packageRoot": str(root),
        "sectionFiles": section_names,
        "completeFile": complete_name,
    }


def _choose_output_mode(engine) -> str:
    labels = {
        "Solo completo": "complete_only",
        "Completo + secciones": "complete_and_sections",
        "Solo secciones": "sections_only",
    }
    if sys.platform == "darwin" and hasattr(engine, "_osascript"):
        rc, out = engine._osascript([
            'set r to display dialog "MODO DE SALIDA\\n\\nElige qué quieres recibir para esta exportación." buttons {"Solo completo", "Solo secciones", "Completo + secciones"} default button "Completo + secciones"',
            'return button returned of r',
        ])
        if rc == 0 and out in labels:
            return labels[out]
        return DEFAULT_NEW_SETUP_MODE
    raw = input("Modo [1=solo completo, 2=completo+secciones, 3=solo secciones] (2): ").strip()
    return {"1": "complete_only", "2": "complete_and_sections", "3": "sections_only", "": DEFAULT_NEW_SETUP_MODE}.get(raw, DEFAULT_NEW_SETUP_MODE)


def _mode_label(mode: str) -> str:
    return {
        "complete_only": "Solo video completo",
        "complete_and_sections": "Video completo + secciones individuales",
        "sections_only": "Solo secciones individuales",
    }[normalize_output_mode(mode)]


def _config_file_from_output_root(output_root: str) -> Path:
    return Path(output_root).expanduser().resolve().parent / "ABRXOS_MULTI_CUTTER_CONFIG.json"


def _cache_parts(engine, root: Path, job: Dict[str, Any], encoder: str, source_fp_cache: Dict[str, Dict[str, Any]], state: Dict[str, Any], ffprobe: str, ffmpeg: str) -> List[Path]:
    jid = job["job_id"]
    item = state["items"][jid]
    source = Path(job["master"]).expanduser().resolve()
    fp = source_fp_cache.get(str(source))
    if fp is None:
        fp = engine.fast_file_fingerprint(source)
        source_fp_cache[str(source)] = fp
    cache_root = engine.control_dir(root) / "CACHE_PARTS" / engine.safe_id(job["master_group"]) / job["orientation"].upper()
    total = len(job["segments"])
    parts: List[Path] = []
    for idx, seg in enumerate(job["segments"], 1):
        ck = engine.cache_key(fp, job["orientation"], seg, encoder)
        part = cache_root / f"{engine.safe_id(job['piece_id'])}__P{idx:02d}__{ck}.mp4"
        parts.append(part)
        if engine.output_is_valid(ffprobe, part, seg["duration"]):
            item["progress"] = (idx / total) * 88.0
            item["detail"] = f"PART {idx}/{total} · cache"
            engine.save_state(root, state)
            continue

        def cb(frac: float, idx=idx):
            base = ((idx - 1) / total) * 88.0
            span = (1.0 / total) * 88.0
            item["progress"] = base + span * frac
            item["detail"] = f"ENCODE PART {idx}/{total}"
            item["updated_at"] = engine.now_iso()
            engine.save_state(root, state)

        engine.ffmpeg_encode_part(ffmpeg, source, seg["start"], seg["end"], part, encoder, on_progress=cb)
        if not engine.output_is_valid(ffprobe, part, seg["duration"]):
            raise RuntimeError(f"PART inválida tras render: {part.name}")
    return parts


def _process_job_v310(engine, root: Path, job: Dict[str, Any], state: Dict[str, Any], ffmpeg: str, ffprobe: str, encoder: str, source_fp_cache: Dict[str, Dict[str, Any]]):
    mode = normalize_output_mode(getattr(engine, "_ABRXOS_OUTPUT_MODE", DEFAULT_LEGACY_MODE))
    jid = job["job_id"]
    item = state["items"][jid]
    output = engine.job_output(root, job)
    output.parent.mkdir(parents=True, exist_ok=True)

    item.update(status="PROCESSING", progress=0.0, detail=f"MODO · {_mode_label(mode)}", updated_at=engine.now_iso())
    state["current_job_id"] = jid
    engine.save_state(root, state)

    parts = _cache_parts(engine, root, job, encoder, source_fp_cache, state, ffprobe, ffmpeg)

    if wants_complete(mode):
        if not engine.output_is_valid(ffprobe, output, job["expected_cut_duration"]):
            item["progress"] = 91.0
            item["detail"] = "ENSAMBLANDO COMPLETO"
            engine.save_state(root, state)
            if len(parts) == 1:
                tmp = output.with_name(output.stem + ".partial" + output.suffix)
                shutil.copy2(parts[0], tmp)
                os.replace(tmp, output)
            else:
                engine.concat_parts(ffmpeg, parts, output)
        item["progress"] = 95.0
        item["detail"] = "VERIFICANDO COMPLETO"
        engine.save_state(root, state)
        if not engine.output_is_valid(ffprobe, output, job["expected_cut_duration"]):
            raise RuntimeError(f"Output final no pasó QA de duración: {output}")

    if wants_sections(mode) or mode == "complete_and_sections":
        item["progress"] = 97.0
        item["detail"] = "EXPORTANDO PAQUETE CAPCUT"
        engine.save_state(root, state)
        export_capcut_package(output, job, mode, parts)
    elif mode == "complete_only":
        # Keep legacy output behavior exactly. No extra package required.
        pass

    source = Path(job["master"]).expanduser().resolve()
    fp = source_fp_cache.get(str(source)) or engine.fast_file_fingerprint(source)
    if wants_complete(mode):
        engine.atomic_json(output.with_suffix(".json"), {
            "schema_version": "abrxos.cut-output.v2",
            "job": job,
            "source_fingerprint": fp,
            "render_profile": engine.RENDER_PROFILE_ID,
            "encoder": encoder,
            "output_mode": mode,
            "cutter_version": CAPCUT_LAYER_VERSION,
            "finished_at": engine.now_iso(),
        })

    item.update(status="DONE", progress=100.0, detail=f"LISTO · {_mode_label(mode)}", updated_at=engine.now_iso())
    engine.save_state(root, state)
    engine.log(root, f"DONE {job['piece_id']} {job['orientation']} mode={mode} -> {output.parent}")


def install(engine) -> None:
    """Install the additive layer into the already-loaded Cutter engine."""
    if getattr(engine, "_ABRXOS_CAPCUT_V310_INSTALLED", False):
        return
    engine._ABRXOS_CAPCUT_V310_INSTALLED = True
    engine.CUTTER_PRODUCT_VERSION = CAPCUT_LAYER_VERSION

    original_interactive_setup = engine.interactive_setup
    original_run_plan = engine.run_plan
    original_process_job = engine.process_job

    def interactive_setup_v310():
        config = original_interactive_setup()
        if not config:
            return config
        mode = _choose_output_mode(engine)
        config["output_mode"] = mode
        config.setdefault("notes", {})["capcut_export_mode"] = mode
        config.setdefault("notes", {})["capcut_export_version"] = CAPCUT_LAYER_VERSION
        config_path = _config_file_from_output_root(config["output_root"])
        engine.atomic_json(config_path, config)
        print(f"✓ Modo de salida: {_mode_label(mode)}")
        return config

    def run_plan_v310(config, plan):
        engine._ABRXOS_OUTPUT_MODE = normalize_output_mode(config.get("output_mode", DEFAULT_LEGACY_MODE))
        print(f"Modo de salida: {_mode_label(engine._ABRXOS_OUTPUT_MODE)}")
        return original_run_plan(config, plan)

    def process_job_v310(root, job, state, ffmpeg, ffprobe, encoder, source_fp_cache):
        mode = normalize_output_mode(getattr(engine, "_ABRXOS_OUTPUT_MODE", DEFAULT_LEGACY_MODE))
        if mode == "complete_only":
            return original_process_job(root, job, state, ffmpeg, ffprobe, encoder, source_fp_cache)
        return _process_job_v310(engine, root, job, state, ffmpeg, ffprobe, encoder, source_fp_cache)

    engine.interactive_setup = interactive_setup_v310
    engine.run_plan = run_plan_v310
    engine.process_job = process_job_v310

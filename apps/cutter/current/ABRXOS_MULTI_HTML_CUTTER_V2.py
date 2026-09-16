#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ABRXOS MULTI HTML CUTTER V2
macOS · HTML-driven · multiple source groups · optional vertical/horizontal masters

Objetivo:
- Seleccionar varios HTML.
- Detectar uno o varios grupos de fuente dentro de cada HTML.
- Reutilizar el mismo master entre HTML que comparten proyecto/fuente.
- Permitir master V, H, ambos o ninguno por fuente.
- Cada ficha/contenido = UN video final por orientación producida.
- Hook/desarrollo/cierre/rangos internos = PARTS internas, nunca videos finales separados.
- Orden de trabajo: INTROS -> VERTICALES -> HORIZONTALES.
- No corta episodios completos.
- No corta carruseles/estáticos.
- Mantiene estado reanudable y visor de Terminal.

No requiere librerías Python externas.
Sí requiere FFmpeg + ffprobe para renderizar.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "2.0.0"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
HTML_EXTS = {".html", ".htm"}

INTRO_TYPES = {"intro", "trailer", "cold_open"}
VERTICAL_TYPES = {"vertical", "vertical_clip", "short_vertical", "short", "reel"}
HORIZONTAL_TYPES = {"horizontal", "horizontal_clip", "horizontal_video", "long_horizontal"}
GENERIC_VIDEO_TYPES = {"video", "clip", "video_clip"}
SKIP_TYPES = {"carousel", "carrusel", "quote", "phrase", "claim", "note", "thread", "pdf", "static", "full_episode", "episode"}

RENDER_PROFILE_ID = "APPLE_VT_H264_40M_V2"
VIDEO_BITRATE = "40M"
AUDIO_BITRATE = "192k"


# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def slug(value: str, limit: int = 74) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.upper()
    value = re.sub(r"[^A-Z0-9]+", "_", value).strip("_")
    value = re.sub(r"_+", "_", value)
    return (value[:limit].rstrip("_") or "SIN_TITULO")


def safe_id(value: str) -> str:
    return slug(value, 48)


def seconds_from_any(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", ".")
    if not s:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)
    parts = s.split(":")
    try:
        nums = [float(x) for x in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 1:
        return nums[0]
    return None


def tc(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    sec -= h * 3600
    m = int(sec // 60)
    sec -= m * 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def atomic_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def fast_file_fingerprint(path: Path) -> Dict[str, Any]:
    st = path.stat()
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    h.update(str(st.st_mtime_ns).encode())
    sample = 4 * 1024 * 1024
    with path.open("rb") as f:
        head = f.read(sample)
        h.update(head)
        if st.st_size > sample:
            try:
                f.seek(max(0, st.st_size - sample))
                h.update(f.read(sample))
            except OSError:
                pass
    return {
        "path": str(path.resolve()),
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sample_sha256": h.hexdigest(),
    }


def run_capture(cmd: List[str]) -> Tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout or ""


def find_binary(name: str) -> Optional[str]:
    candidates = [
        shutil.which(name),
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
        f"/usr/bin/{name}",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def probe_duration(ffprobe: str, path: Path) -> Optional[float]:
    rc, out = run_capture([
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ])
    if rc != 0:
        return None
    try:
        return float(out.strip())
    except Exception:
        return None


def has_videotoolbox(ffmpeg: str) -> bool:
    rc, out = run_capture([ffmpeg, "-hide_banner", "-encoders"])
    return rc == 0 and "h264_videotoolbox" in out


# ---------------------------------------------------------------------------
# SELECTORES NATIVOS DE macOS
# ---------------------------------------------------------------------------

def _osascript(lines: List[str], argv: Optional[List[str]] = None) -> Tuple[int, str]:
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return 127, ""
    cmd = ["osascript"]
    for line in lines:
        cmd += ["-e", line]
    if argv:
        cmd += ["--", *argv]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, (p.stdout or "").strip()


def choose_htmls() -> List[Path]:
    rc, out = _osascript([
        'set fs to choose file with prompt "Selecciona uno o varios HTML de contenido" with multiple selections allowed',
        'set o to ""',
        'repeat with f in fs',
        'set o to o & POSIX path of f & linefeed',
        'end repeat',
        'return o'
    ])
    if rc == 0 and out:
        paths = [Path(x.strip()).expanduser() for x in out.splitlines() if x.strip()]
        return [p for p in paths if p.suffix.lower() in HTML_EXTS]
    if sys.platform == "darwin":
        return []
    raw = input("Rutas HTML separadas por coma: ").strip()
    return [Path(x.strip()).expanduser() for x in raw.split(",") if x.strip()]


def choose_optional_video(prompt: str) -> Optional[Path]:
    # Primero se pregunta explícitamente Seleccionar/Omitir.
    rc, out = _osascript([
        'on run argv',
        'set msg to item 1 of argv',
        'set r to display dialog msg buttons {"Omitir", "Seleccionar"} default button "Seleccionar" cancel button "Omitir"',
        'return button returned of r',
        'end run'
    ], [prompt])
    if rc != 0 or out != "Seleccionar":
        return None

    rc, out = _osascript([
        'on run argv',
        'set msg to item 1 of argv',
        'set f to choose file with prompt msg',
        'return POSIX path of f',
        'end run'
    ], [prompt])
    if rc == 0 and out:
        p = Path(out).expanduser()
        if p.suffix.lower() not in VIDEO_EXTS:
            print(f"⚠️  Archivo no reconocido como video: {p.name}. Se aceptará igualmente.")
        return p
    return None


def choose_output_parent() -> Optional[Path]:
    rc, out = _osascript([
        'set f to choose folder with prompt "Selecciona la carpeta donde crear ABRXOS_EXPORT"',
        'return POSIX path of f'
    ])
    if rc == 0 and out:
        return Path(out).expanduser()
    if sys.platform != "darwin":
        raw = input("Carpeta de salida: ").strip()
        return Path(raw).expanduser() if raw else None
    return None


# ---------------------------------------------------------------------------
# PARSEO HTML
# ---------------------------------------------------------------------------

SCRIPT_IDS = ("app-data", "editorialData")


def extract_json_script(raw_html: str) -> Tuple[str, Dict[str, Any]]:
    # Primero app-data porque es el formato de los Story Editor reales actuales.
    for sid in SCRIPT_IDS:
        pat = rf'<script[^>]+id=["\']{re.escape(sid)}["\'][^>]*>(.*?)</script>'
        m = re.search(pat, raw_html, re.I | re.S)
        if not m:
            continue
        body = html_lib.unescape(m.group(1).strip())
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                return sid, data
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"JSON inválido dentro de script#{sid}: {exc}")
    raise RuntimeError("No se encontró script#app-data ni script#editorialData con JSON válido.")


def editorial_to_pieces(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(data.get("pieces"), list):
        return [dict(x) for x in data["pieces"] if isinstance(x, dict)]

    out: List[Dict[str, Any]] = []
    mapping = {
        "intros": "intro",
        "verticals": "vertical",
        "horizontals": "horizontal",
    }
    for key, ptype in mapping.items():
        items = data.get(key, [])
        if not isinstance(items, list):
            continue
        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            x = dict(item)
            x.setdefault("id", x.get("content_id") or x.get("canonicalId") or f"{ptype}_{i:02d}")
            x.setdefault("type", ptype)
            out.append(x)
    return out


def canonical_project_id(data: Dict[str, Any], pieces: List[Dict[str, Any]]) -> str:
    ids = [
        clean_text(p.get("projectId"))
        for p in pieces
        if clean_text(p.get("projectId"))
    ]
    if ids:
        common = Counter(ids).most_common(1)[0][0]
        return common
    return clean_text(data.get("projectId") or data.get("project_id") or data.get("title") or "PROJECT")


def source_label(code: str, meta: Any) -> str:
    if isinstance(meta, dict):
        bits = [clean_text(meta.get("name")), clean_text(meta.get("kind"))]
        bits = [x for x in bits if x]
        if bits:
            return " · ".join(dict.fromkeys(bits))
    return code if code != "DEFAULT" else "Fuente principal"


@dataclass
class HtmlDoc:
    path: str
    script_id: str
    root_project_id: str
    canonical_project_id: str
    title: str
    sources: Dict[str, Dict[str, Any]]
    pieces: List[Dict[str, Any]]


def parse_html(path: Path) -> HtmlDoc:
    raw = read_text(path)
    sid, data = extract_json_script(raw)
    pieces = editorial_to_pieces(data)
    project = canonical_project_id(data, pieces)
    root_project = clean_text(data.get("projectId") or project)

    declared_sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    used_sources = {
        clean_text(p.get("source"))
        for p in pieces
        if clean_text(p.get("source"))
    }

    sources: Dict[str, Dict[str, Any]] = {}
    if declared_sources:
        # Solo fuentes realmente usadas por piezas de video/edición.
        keys = used_sources or set(declared_sources.keys())
        for code in declared_sources:
            if code in keys:
                meta = declared_sources.get(code)
                sources[code] = dict(meta) if isinstance(meta, dict) else {"name": code}
    elif used_sources:
        for code in sorted(used_sources):
            sources[code] = {"name": code}
    else:
        sources["DEFAULT"] = {
            "name": clean_text(
                data.get("episode", {}).get("title") if isinstance(data.get("episode"), dict) else ""
            ) or clean_text(data.get("title")) or project
        }

    title = (
        clean_text(data.get("title"))
        or clean_text(data.get("episode", {}).get("title") if isinstance(data.get("episode"), dict) else "")
        or path.stem
    )

    return HtmlDoc(
        path=str(path.resolve()),
        script_id=sid,
        root_project_id=root_project,
        canonical_project_id=project,
        title=title,
        sources=sources,
        pieces=pieces,
    )


# ---------------------------------------------------------------------------
# NORMALIZACIÓN DE FUENTES / PIEZAS
# ---------------------------------------------------------------------------

def piece_source_code(piece: Dict[str, Any], doc: HtmlDoc) -> str:
    src = clean_text(piece.get("source"))
    if src:
        return src
    if len(doc.sources) == 1:
        return next(iter(doc.sources))
    return "DEFAULT"


def master_group_key(doc: HtmlDoc, source_code: str, piece: Optional[Dict[str, Any]] = None) -> str:
    # La identidad de proyecto por pieza permite que HTML de intros derivados
    # reutilicen los masters del HTML principal.
    p_project = clean_text(piece.get("projectId")) if piece else ""
    project = p_project or doc.canonical_project_id
    return f"{project}::{source_code}"


def piece_id(piece: Dict[str, Any], idx: int) -> str:
    return clean_text(
        piece.get("canonicalId")
        or piece.get("content_id")
        or piece.get("contentId")
        or piece.get("id")
        or f"PIECE_{idx:03d}"
    )


def piece_title(piece: Dict[str, Any], pid: str) -> str:
    return clean_text(piece.get("title") or piece.get("workingTitle") or piece.get("headline") or pid)


def piece_type(piece: Dict[str, Any]) -> str:
    return clean_text(piece.get("type") or piece.get("kind") or piece.get("physical_type")).lower()


def is_video_piece(piece: Dict[str, Any]) -> bool:
    ptype = piece_type(piece)
    return ptype in INTRO_TYPES | VERTICAL_TYPES | HORIZONTAL_TYPES | GENERIC_VIDEO_TYPES


def extract_segments(piece: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Any] = []

    for key in ("sourceRanges", "segments", "parts", "newRanges"):
        val = piece.get(key)
        if isinstance(val, list) and val:
            candidates = val
            break

    out: List[Dict[str, Any]] = []
    for i, r in enumerate(candidates, 1):
        if not isinstance(r, dict):
            continue

        start = (
            seconds_from_any(r.get("start"))
            if r.get("start") is not None
            else seconds_from_any(r.get("sourceStart") or r.get("in") or r.get("source_in"))
        )
        end = (
            seconds_from_any(r.get("end"))
            if r.get("end") is not None
            else seconds_from_any(r.get("sourceEnd") or r.get("out") or r.get("source_out"))
        )

        # Algunos manifests usan {a,b} como cue IDs, no como segundos: no usar esos campos.
        if start is None or end is None or end <= start:
            continue

        out.append({
            "index": i,
            "order": r.get("order", i),
            "start": float(start),
            "end": float(end),
            "duration": float(end - start),
            "role": clean_text(r.get("role")),
            "speaker": clean_text(r.get("speaker")),
            "text": clean_text(r.get("text") or r.get("source_literal") or r.get("sourceLiteral")),
        })

    # Conservar el orden editorial del array. No ordenar por cronología del master.
    return out


def target_orientations(piece: Dict[str, Any], masters: Dict[str, Optional[str]]) -> List[str]:
    ptype = piece_type(piece)
    v = bool(masters.get("vertical"))
    h = bool(masters.get("horizontal"))

    if ptype in INTRO_TYPES:
        return [x for x, ok in (("vertical", v), ("horizontal", h)) if ok]
    if ptype in VERTICAL_TYPES:
        return ["vertical"] if v else []
    if ptype in HORIZONTAL_TYPES:
        return ["horizontal"] if h else []
    if ptype in GENERIC_VIDEO_TYPES:
        # Video genérico se produce en las orientaciones realmente disponibles.
        return [x for x, ok in (("vertical", v), ("horizontal", h)) if ok]
    return []


def phase_for(piece: Dict[str, Any], orientation: str) -> str:
    ptype = piece_type(piece)
    if ptype in INTRO_TYPES:
        return "01_INTROS"
    if orientation == "vertical":
        return "02_VERTICALES"
    return "03_HORIZONTALES"


def phase_rank(phase: str) -> int:
    return {"01_INTROS": 1, "02_VERTICALES": 2, "03_HORIZONTALES": 3}.get(phase, 99)


# ---------------------------------------------------------------------------
# CONFIGURACIÓN INTERACTIVA
# ---------------------------------------------------------------------------

def build_source_inventory(docs: List[HtmlDoc]) -> Dict[str, Dict[str, Any]]:
    inv: Dict[str, Dict[str, Any]] = {}

    for doc in docs:
        # Identificar qué source group usa cada pieza.
        grouped_piece_ids: Dict[str, List[str]] = defaultdict(list)
        for i, p in enumerate(doc.pieces, 1):
            if not is_video_piece(p):
                continue
            src = piece_source_code(p, doc)
            grouped_piece_ids[src].append(piece_id(p, i))

        for src_code, pids in grouped_piece_ids.items():
            # Si una pieza lleva projectId, este HTML puede compartir master con otro HTML.
            sample_piece = next(
                (p for p in doc.pieces if is_video_piece(p) and piece_source_code(p, doc) == src_code),
                None,
            )
            key = master_group_key(doc, src_code, sample_piece)
            meta = doc.sources.get(src_code, {"name": src_code})
            if key not in inv:
                inv[key] = {
                    "key": key,
                    "project_id": key.split("::", 1)[0],
                    "source_code": src_code,
                    "label": source_label(src_code, meta),
                    "htmls": [],
                    "piece_count": 0,
                    "piece_ids": [],
                }
            inv[key]["htmls"].append(doc.path)
            inv[key]["piece_count"] += len(pids)
            inv[key]["piece_ids"].extend(pids)

    return inv


def interactive_setup() -> Optional[Dict[str, Any]]:
    print("\nABRXOS MULTI HTML CUTTER V2")
    print("Selecciona primero los HTML. Después asignaremos masters por FUENTE.\n")

    html_paths = choose_htmls()
    if not html_paths:
        print("No seleccionaste HTML. Cancelado.")
        return None

    docs: List[HtmlDoc] = []
    for p in html_paths:
        try:
            d = parse_html(p)
            docs.append(d)
            print(f"✓ {p.name} · {len(d.pieces)} piezas · JSON #{d.script_id}")
        except Exception as exc:
            print(f"✗ {p.name}: {exc}")

    if not docs:
        print("No hay HTML válidos.")
        return None

    inventory = build_source_inventory(docs)
    if not inventory:
        print("No se detectaron piezas de video producibles.")
        return None

    print("\nFUENTES DETECTADAS")
    for n, item in enumerate(inventory.values(), 1):
        html_names = sorted({Path(x).name for x in item["htmls"]})
        print(f"{n:02d}. {item['project_id']} / {item['source_code']} · {item['label']}")
        print(f"    {item['piece_count']} piezas · {', '.join(html_names)}")

    masters: Dict[str, Dict[str, Optional[str]]] = {}
    for n, (key, item) in enumerate(inventory.items(), 1):
        label = f"{item['project_id']} · {item['label']} [{item['source_code']}]"
        print(f"\n[{n}/{len(inventory)}] {label}")
        v = choose_optional_video(f"{label}\n\nMASTER VERTICAL\nSelecciona el video vertical o pulsa Omitir.")
        print("  Vertical:", v.name if v else "— OMITIDO")
        h = choose_optional_video(f"{label}\n\nMASTER HORIZONTAL\nSelecciona el video horizontal o pulsa Omitir.")
        print("  Horizontal:", h.name if h else "— OMITIDO")
        masters[key] = {
            "vertical": str(v.resolve()) if v else None,
            "horizontal": str(h.resolve()) if h else None,
        }

    parent = choose_output_parent()
    if not parent:
        print("No seleccionaste carpeta de salida. Cancelado.")
        return None

    root_name = "ABRXOS_EXPORT_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = parent / root_name

    config = {
        "schema_version": "abrxos.multi-html-cutter.v2",
        "version": VERSION,
        "created_at": now_iso(),
        "htmls": [d.path for d in docs],
        "masters": masters,
        "output_root": str(output_root.resolve()),
        "render_profile": RENDER_PROFILE_ID,
        "notes": {
            "one_piece_one_video": True,
            "hook_development_close_are_internal_parts": True,
            "phase_order": ["intros", "verticals", "horizontals"],
            "skip_full_episode": True,
        },
    }

    config_path = parent / "ABRXOS_MULTI_CUTTER_CONFIG.json"
    atomic_json(config_path, config)
    print(f"\n✓ Configuración guardada:\n{config_path}")
    return config


# ---------------------------------------------------------------------------
# PLAN
# ---------------------------------------------------------------------------

def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(read_text(path))


def resolve_docs(config: Dict[str, Any]) -> List[HtmlDoc]:
    docs = []
    for p in config.get("htmls", []):
        path = Path(p).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"HTML no encontrado: {path}")
        docs.append(parse_html(path))
    return docs


def lookup_masters(config: Dict[str, Any], doc: HtmlDoc, piece: Dict[str, Any]) -> Tuple[str, Dict[str, Optional[str]]]:
    src = piece_source_code(piece, doc)
    key = master_group_key(doc, src, piece)
    masters = config.get("masters", {}).get(key)
    if masters is None:
        # Fallback: a veces el root project del HTML fue usado en una config anterior.
        alt = f"{doc.canonical_project_id}::{src}"
        masters = config.get("masters", {}).get(alt, {})
        key = alt if masters else key
    return key, {
        "vertical": masters.get("vertical") if isinstance(masters, dict) else None,
        "horizontal": masters.get("horizontal") if isinstance(masters, dict) else None,
    }


def make_plan(config: Dict[str, Any]) -> Dict[str, Any]:
    docs = resolve_docs(config)
    jobs: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    seen_job_keys = set()

    for doc_index, doc in enumerate(docs, 1):
        for i, p in enumerate(doc.pieces, 1):
            pid = piece_id(p, i)
            title = piece_title(p, pid)
            ptype = piece_type(p)

            if ptype in SKIP_TYPES or not is_video_piece(p):
                skipped.append({
                    "html": doc.path, "id": pid, "type": ptype,
                    "reason": "NO_VIDEO_O_EXCLUIDO"
                })
                continue

            segs = extract_segments(p)
            if not segs:
                skipped.append({
                    "html": doc.path, "id": pid, "type": ptype,
                    "reason": "SIN_RANGOS_VALIDOS"
                })
                continue

            master_key, masters = lookup_masters(config, doc, p)
            orientations = target_orientations(p, masters)
            if not orientations:
                skipped.append({
                    "html": doc.path, "id": pid, "type": ptype,
                    "reason": "SIN_MASTER_COMPATIBLE",
                    "master_group": master_key,
                })
                continue

            for ori in orientations:
                master = masters.get(ori)
                if not master:
                    continue
                job_key = (doc.canonical_project_id, pid, ori, master_key)
                if job_key in seen_job_keys:
                    # Evita duplicado accidental del mismo HTML/pieza.
                    continue
                seen_job_keys.add(job_key)

                phase = phase_for(p, ori)
                project_folder = safe_id(doc.canonical_project_id)
                source_code = piece_source_code(p, doc)
                source_folder = safe_id(source_code) if source_code != "DEFAULT" else ""
                content_folder = f"{safe_id(pid)}__{slug(title, 52)}"
                filename = f"{safe_id(pid)}__{slug(title, 52)}__{ori.upper()}.mp4"

                folder_parts = [project_folder, phase]
                if source_folder:
                    folder_parts.append(source_folder)
                folder_parts.append(content_folder)

                jobs.append({
                    "job_id": sha256_text("|".join(map(str, job_key)))[:16],
                    "project_id": doc.canonical_project_id,
                    "html": doc.path,
                    "html_name": Path(doc.path).name,
                    "master_group": master_key,
                    "source_code": source_code,
                    "piece_id": pid,
                    "title": title,
                    "piece_type": ptype,
                    "orientation": ori,
                    "phase": phase,
                    "master": master,
                    "segments": segs,
                    "output_relative": str(Path(*folder_parts) / filename),
                    "segment_count": len(segs),
                    "expected_cut_duration": round(sum(s["duration"] for s in segs), 3),
                })

    jobs.sort(key=lambda j: (
        phase_rank(j["phase"]),
        j["project_id"],
        j["source_code"],
        j["piece_id"],
        0 if j["orientation"] == "vertical" else 1,
    ))

    counts = Counter(j["phase"] for j in jobs)
    return {
        "schema_version": "abrxos.cut-plan.v2",
        "created_at": now_iso(),
        "output_root": config["output_root"],
        "job_count": len(jobs),
        "counts": dict(counts),
        "jobs": jobs,
        "skipped": skipped,
    }


def print_plan(plan: Dict[str, Any]):
    print("\n" + "=" * 72)
    print("ABRXOS · PLAN DE CORTE")
    print("=" * 72)
    print(f"TOTAL MP4 FINALES: {plan['job_count']}")
    print(f"INTROS:      {plan['counts'].get('01_INTROS', 0)}")
    print(f"VERTICALES:  {plan['counts'].get('02_VERTICALES', 0)}")
    print(f"HORIZONTALES:{plan['counts'].get('03_HORIZONTALES', 0)}")
    print(f"OMITIDOS:    {len(plan.get('skipped', []))}")
    print()

    for phase in ("01_INTROS", "02_VERTICALES", "03_HORIZONTALES"):
        rows = [j for j in plan["jobs"] if j["phase"] == phase]
        if not rows:
            continue
        print(phase)
        for j in rows:
            print(
                f"  {j['piece_id']:<22} {j['orientation'][0].upper()} · "
                f"{j['segment_count']} rango(s) · {j['expected_cut_duration']:.1f}s · {j['title']}"
            )
        print()


# ---------------------------------------------------------------------------
# STATE / MONITOR
# ---------------------------------------------------------------------------

def control_dir(root: Path) -> Path:
    return root / "00_CONTROL"


def state_paths(root: Path) -> Tuple[Path, Path]:
    return control_dir(root) / "STATE.json", root / "ABRXOS_STATUS.json"


def initial_state(plan: Dict[str, Any]) -> Dict[str, Any]:
    items = {}
    for j in plan["jobs"]:
        items[j["job_id"]] = {
            "job_id": j["job_id"],
            "piece_id": j["piece_id"],
            "title": j["title"],
            "phase": j["phase"],
            "orientation": j["orientation"],
            "status": "PENDING",
            "progress": 0.0,
            "detail": "",
            "output_relative": j["output_relative"],
            "updated_at": now_iso(),
        }
    return {
        "schema_version": "abrxos.cutter-state.v2",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "current_job_id": None,
        "total": len(items),
        "items": items,
        "last_error": None,
    }


def save_state(root: Path, state: Dict[str, Any]):
    state["updated_at"] = now_iso()
    a, b = state_paths(root)
    atomic_json(a, state)
    atomic_json(b, state)

    done, pending, failed = [], [], []
    for item in state["items"].values():
        line = f"{item['piece_id']} · {item['orientation'].upper()} · {item['title']}"
        if item["status"] in {"DONE", "SKIPPED_VALID"}:
            done.append(line)
        elif item["status"] == "FAILED":
            failed.append(line + " · " + item.get("detail", ""))
        else:
            pending.append(line)

    c = control_dir(root)
    c.mkdir(parents=True, exist_ok=True)
    (c / "HECHOS.txt").write_text("\n".join(done) + ("\n" if done else ""), encoding="utf-8")
    (c / "PENDIENTES.txt").write_text("\n".join(pending) + ("\n" if pending else ""), encoding="utf-8")
    (c / "FALLIDOS.txt").write_text("\n".join(failed) + ("\n" if failed else ""), encoding="utf-8")


def log(root: Path, text: str):
    c = control_dir(root)
    c.mkdir(parents=True, exist_ok=True)
    with (c / "HISTORIAL.log").open("a", encoding="utf-8") as f:
        f.write(f"{now_iso()} · {text}\n")


def state_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    items = list(state.get("items", {}).values())
    done = [x for x in items if x.get("status") in {"DONE", "SKIPPED_VALID"}]
    failed = [x for x in items if x.get("status") == "FAILED"]
    processing = [x for x in items if x.get("status") == "PROCESSING"]
    total = len(items)
    general = (len(done) / total * 100.0) if total else 100.0
    phases = {}
    for phase in ("01_INTROS", "02_VERTICALES", "03_HORIZONTALES"):
        rows = [x for x in items if x.get("phase") == phase]
        d = [x for x in rows if x.get("status") in {"DONE", "SKIPPED_VALID"}]
        phases[phase] = {
            "done": len(d),
            "total": len(rows),
            "pct": (len(d) / len(rows) * 100.0) if rows else 100.0,
        }
    return {
        "total": total,
        "done": len(done),
        "failed": len(failed),
        "processing": processing,
        "pct": general,
        "phases": phases,
    }


def bar(pct: float, width: int = 30) -> str:
    pct = max(0.0, min(100.0, pct))
    fill = int(round(width * pct / 100.0))
    return "█" * fill + "░" * (width - fill)


def monitor(root: Path, interval: float = 1.0):
    root = root.expanduser().resolve()
    a, b = state_paths(root)
    path = a if a.exists() else b
    if not path.exists():
        raise SystemExit(
            f"No encuentro STATE.json ni ABRXOS_STATUS.json en:\n{root}\n"
            f"Esperado: {a}"
        )

    try:
        while True:
            try:
                state = json.loads(read_text(path))
            except Exception:
                time.sleep(interval)
                continue

            s = state_summary(state)
            os.system("clear")
            print("ABRXOS CUTTING MONITOR V2")
            print("=" * 72)
            print(f"ROOT: {root}")
            print(f"ACTUALIZADO: {state.get('updated_at', '—')}")
            print()
            print(f"GENERAL  [{bar(s['pct'])}] {s['pct']:6.2f}%")
            print(f"Hechos {s['done']}/{s['total']} · Fallidos {s['failed']}")
            print()

            labels = {
                "01_INTROS": "INTROS",
                "02_VERTICALES": "VERTICALES",
                "03_HORIZONTALES": "HORIZONTALES",
            }
            for phase, label in labels.items():
                p = s["phases"][phase]
                print(f"{label:<12}[{bar(p['pct'], 22)}] {p['pct']:6.2f}%  {p['done']}/{p['total']}")

            current_id = state.get("current_job_id")
            current = state.get("items", {}).get(current_id) if current_id else None
            print("\nVIDEO ACTUAL")
            if current:
                print(f"{current['piece_id']} · {current['orientation'].upper()}")
                print(current["title"])
                print(f"{current['status']} · {current.get('progress', 0):.1f}% · {current.get('detail', '')}")
            else:
                print("—")

            print("\nCtrl+C para cerrar el visor. El render continúa en la otra Terminal.")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nVisor cerrado.")


# ---------------------------------------------------------------------------
# RENDER ENGINE
# ---------------------------------------------------------------------------

def validate_master_paths(plan: Dict[str, Any]):
    missing = sorted({j["master"] for j in plan["jobs"] if not Path(j["master"]).exists()})
    if missing:
        raise FileNotFoundError("Masters no encontrados:\n" + "\n".join(missing))


def job_output(root: Path, job: Dict[str, Any]) -> Path:
    return root / job["output_relative"]


def cache_key(master_fp: Dict[str, Any], orientation: str, seg: Dict[str, Any], encoder: str) -> str:
    payload = {
        "source": master_fp,
        "orientation": orientation,
        "start": round(seg["start"], 6),
        "end": round(seg["end"], 6),
        "profile": RENDER_PROFILE_ID,
        "encoder": encoder,
    }
    return sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))[:28]


def ffmpeg_encode_part(
    ffmpeg: str,
    source: Path,
    start: float,
    end: float,
    target: Path,
    encoder: str,
    on_progress=None,
):
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.stem + ".partial" + target.suffix)
    duration = end - start

    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.6f}", "-i", str(source),
        "-t", f"{duration:.6f}",
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", encoder,
    ]

    if encoder == "h264_videotoolbox":
        cmd += [
            "-profile:v", "high",
            "-b:v", VIDEO_BITRATE,
            "-pix_fmt", "yuv420p",
        ]
    else:
        cmd += [
            "-preset", "medium",
            "-crf", "15",
            "-pix_fmt", "yuv420p",
        ]

    cmd += [
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        str(partial),
    ]

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    if p.stdout:
        for line in p.stdout:
            line = line.strip()
            if line.startswith("out_time_ms=") and on_progress:
                try:
                    # ffmpeg tradicionalmente reporta microsegundos bajo este nombre.
                    cur = int(line.split("=", 1)[1]) / 1_000_000.0
                    on_progress(max(0.0, min(1.0, cur / duration)))
                except Exception:
                    pass
    rc = p.wait()
    if rc != 0:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
        raise RuntimeError(f"FFmpeg falló ({rc}) al cortar {source.name} {tc(start)}–{tc(end)}")
    os.replace(partial, target)


def concat_parts(ffmpeg: str, parts: List[Path], target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.stem + ".partial" + target.suffix)
    concat_file = target.parent / f".{target.stem}.concat.txt"

    def quote_concat(p: Path) -> str:
        # Formato concat demuxer: comilla simple y escape de single quotes.
        s = str(p.resolve()).replace("'", "'\\''")
        return f"file '{s}'"

    concat_file.write_text("\n".join(quote_concat(p) for p in parts) + "\n", encoding="utf-8")
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", "-movflags", "+faststart",
        str(partial),
    ]
    rc, out = run_capture(cmd)
    try:
        concat_file.unlink()
    except FileNotFoundError:
        pass
    if rc != 0:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
        raise RuntimeError("Concat -c copy falló:\n" + out[-1800:])
    os.replace(partial, target)


def output_is_valid(ffprobe: str, path: Path, expected: float) -> bool:
    if not path.exists() or path.stat().st_size < 4096:
        return False
    dur = probe_duration(ffprobe, path)
    if dur is None:
        return False
    tolerance = max(0.35, min(1.5, expected * 0.015))
    return abs(dur - expected) <= tolerance


def process_job(
    root: Path,
    job: Dict[str, Any],
    state: Dict[str, Any],
    ffmpeg: str,
    ffprobe: str,
    encoder: str,
    source_fp_cache: Dict[str, Dict[str, Any]],
):
    jid = job["job_id"]
    item = state["items"][jid]
    output = job_output(root, job)
    output.parent.mkdir(parents=True, exist_ok=True)

    if output_is_valid(ffprobe, output, job["expected_cut_duration"]):
        item.update(status="SKIPPED_VALID", progress=100.0, detail="Output válido existente", updated_at=now_iso())
        save_state(root, state)
        log(root, f"SKIPPED_VALID {job['piece_id']} {job['orientation']}")
        return

    source = Path(job["master"]).expanduser().resolve()
    fp = source_fp_cache.get(str(source))
    if fp is None:
        fp = fast_file_fingerprint(source)
        source_fp_cache[str(source)] = fp

    cache_root = control_dir(root) / "CACHE_PARTS" / safe_id(job["master_group"]) / job["orientation"].upper()
    parts: List[Path] = []
    total_segments = len(job["segments"])

    item.update(status="PROCESSING", progress=0.0, detail="Preparando", updated_at=now_iso())
    state["current_job_id"] = jid
    save_state(root, state)

    for idx, seg in enumerate(job["segments"], 1):
        ck = cache_key(fp, job["orientation"], seg, encoder)
        part = cache_root / f"{safe_id(job['piece_id'])}__P{idx:02d}__{ck}.mp4"
        parts.append(part)

        if output_is_valid(ffprobe, part, seg["duration"]):
            base = (idx / total_segments) * 90.0
            item["progress"] = base
            item["detail"] = f"PART {idx}/{total_segments} · cache"
            save_state(root, state)
            continue

        def cb(frac: float):
            base = ((idx - 1) / total_segments) * 90.0
            span = (1.0 / total_segments) * 90.0
            item["progress"] = base + span * frac
            item["detail"] = f"ENCODE PART {idx}/{total_segments}"
            item["updated_at"] = now_iso()
            save_state(root, state)

        ffmpeg_encode_part(
            ffmpeg, source,
            seg["start"], seg["end"],
            part, encoder,
            on_progress=cb,
        )

        if not output_is_valid(ffprobe, part, seg["duration"]):
            raise RuntimeError(f"PART inválida tras render: {part.name}")

    item["progress"] = 93.0
    item["detail"] = "ENSAMBLANDO"
    save_state(root, state)

    if len(parts) == 1:
        # Copiar el PART canónico al destino. No volver a codificar.
        tmp = output.with_name(output.stem + ".partial" + output.suffix)
        shutil.copy2(parts[0], tmp)
        os.replace(tmp, output)
    else:
        concat_parts(ffmpeg, parts, output)

    item["progress"] = 98.0
    item["detail"] = "VERIFICANDO"
    save_state(root, state)

    if not output_is_valid(ffprobe, output, job["expected_cut_duration"]):
        raise RuntimeError(f"Output final no pasó QA de duración: {output}")

    sidecar = output.with_suffix(".json")
    atomic_json(sidecar, {
        "schema_version": "abrxos.cut-output.v2",
        "job": job,
        "source_fingerprint": fp,
        "render_profile": RENDER_PROFILE_ID,
        "encoder": encoder,
        "finished_at": now_iso(),
    })

    item.update(status="DONE", progress=100.0, detail="LISTO", updated_at=now_iso())
    save_state(root, state)
    log(root, f"DONE {job['piece_id']} {job['orientation']} -> {output}")


def run_plan(config: Dict[str, Any], plan: Dict[str, Any]):
    ffmpeg = find_binary("ffmpeg")
    ffprobe = find_binary("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SystemExit(
            "FFmpeg/ffprobe no encontrados.\n\n"
            "Instálalos con Homebrew:\n"
            "  brew install ffmpeg\n"
        )

    validate_master_paths(plan)

    encoder = "h264_videotoolbox" if has_videotoolbox(ffmpeg) else "libx264"
    if encoder != "h264_videotoolbox":
        print("⚠️  h264_videotoolbox no está disponible. Se usará libx264 CRF 15.")

    root = Path(config["output_root"]).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    c = control_dir(root)
    c.mkdir(parents=True, exist_ok=True)

    atomic_json(c / "PLAN.json", plan)
    atomic_json(c / "CONFIG.json", config)

    a, b = state_paths(root)
    if a.exists():
        try:
            state = json.loads(read_text(a))
        except Exception:
            state = initial_state(plan)
    elif b.exists():
        try:
            state = json.loads(read_text(b))
        except Exception:
            state = initial_state(plan)
    else:
        state = initial_state(plan)

    # Añadir jobs nuevos si el plan se amplió.
    for j in plan["jobs"]:
        state.setdefault("items", {})
        if j["job_id"] not in state["items"]:
            state["items"][j["job_id"]] = {
                "job_id": j["job_id"],
                "piece_id": j["piece_id"],
                "title": j["title"],
                "phase": j["phase"],
                "orientation": j["orientation"],
                "status": "PENDING",
                "progress": 0.0,
                "detail": "",
                "output_relative": j["output_relative"],
                "updated_at": now_iso(),
            }
    state["total"] = len(state["items"])
    save_state(root, state)

    print("\nRENDER")
    print(f"FFmpeg: {ffmpeg}")
    print(f"Encoder: {encoder}")
    print(f"Salida: {root}")
    print("Orden: INTROS → VERTICALES → HORIZONTALES")
    print()

    source_fp_cache: Dict[str, Dict[str, Any]] = {}

    for n, job in enumerate(plan["jobs"], 1):
        jid = job["job_id"]
        state["current_job_id"] = jid
        item = state["items"][jid]
        print(f"[{n}/{len(plan['jobs'])}] {job['piece_id']} · {job['orientation'].upper()} · {job['title']}")
        try:
            process_job(root, job, state, ffmpeg, ffprobe, encoder, source_fp_cache)
        except KeyboardInterrupt:
            item["status"] = "PENDING"
            item["detail"] = "Interrumpido por usuario; reanudable"
            state["current_job_id"] = None
            save_state(root, state)
            print("\nInterrumpido. Puedes ejecutar de nuevo y continuará.")
            return
        except Exception as exc:
            item["status"] = "FAILED"
            item["detail"] = str(exc)
            item["progress"] = 0.0
            state["last_error"] = {
                "job_id": jid,
                "message": str(exc),
                "at": now_iso(),
            }
            save_state(root, state)
            log(root, f"FAILED {job['piece_id']} {job['orientation']} · {exc}")
            print(f"  ✗ {exc}")

    state["current_job_id"] = None
    save_state(root, state)
    s = state_summary(state)
    print("\n" + "=" * 72)
    print(f"TERMINADO · {s['done']}/{s['total']} listos · {s['failed']} fallidos")
    print(f"Salida: {root}")
    print("=" * 72)


# ---------------------------------------------------------------------------
# INSPECT
# ---------------------------------------------------------------------------

def inspect_htmls(paths: List[Path]):
    for p in paths:
        d = parse_html(p)
        print("\n" + "=" * 72)
        print(p.name)
        print(f"script: #{d.script_id}")
        print(f"root project: {d.root_project_id}")
        print(f"canonical project: {d.canonical_project_id}")
        print(f"piezas: {len(d.pieces)}")
        print("fuentes:")
        for code, meta in d.sources.items():
            count = sum(1 for x in d.pieces if piece_source_code(x, d) == code)
            print(f"  {code}: {source_label(code, meta)} · {count} piezas")
        counts = Counter(piece_type(x) for x in d.pieces)
        print("tipos:", dict(counts))


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="ABRXOS Multi HTML Cutter V2 · macOS",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("setup", help="Wizard: HTMLs -> fuentes -> masters V/H -> salida")
    p.add_argument("--no-run", action="store_true", help="Solo crear config/plan; no cortar.")

    p = sub.add_parser("plan", help="Construir/mostrar plan desde config")
    p.add_argument("--config", required=True)

    p = sub.add_parser("run", help="Renderizar/reanudar desde config")
    p.add_argument("--config", required=True)

    p = sub.add_parser("monitor", help="Visor en otra pestaña de Terminal")
    p.add_argument("output_root")
    p.add_argument("--interval", type=float, default=1.0)

    p = sub.add_parser("inspect", help="Inspeccionar uno o más HTML")
    p.add_argument("html", nargs="+")

    return ap


def main():
    ap = parser()
    args = ap.parse_args()

    # Sin comando = wizard completo.
    if not args.cmd:
        config = interactive_setup()
        if not config:
            return
        plan = make_plan(config)
        root = Path(config["output_root"])
        root.mkdir(parents=True, exist_ok=True)
        atomic_json(control_dir(root) / "PLAN.json", plan)
        print_plan(plan)

        answer = input("¿Comenzar a cortar ahora? [S/n]: ").strip().lower()
        if answer in {"", "s", "si", "sí", "y", "yes"}:
            run_plan(config, plan)
        else:
            print("Plan guardado. Puedes ejecutar después con el comando RUN.")
        return

    if args.cmd == "setup":
        config = interactive_setup()
        if not config:
            return
        plan = make_plan(config)
        root = Path(config["output_root"])
        root.mkdir(parents=True, exist_ok=True)
        atomic_json(control_dir(root) / "PLAN.json", plan)
        print_plan(plan)
        if not args.no_run:
            answer = input("¿Comenzar a cortar ahora? [S/n]: ").strip().lower()
            if answer in {"", "s", "si", "sí", "y", "yes"}:
                run_plan(config, plan)
        return

    if args.cmd == "plan":
        config = load_config(Path(args.config).expanduser())
        plan = make_plan(config)
        print_plan(plan)
        root = Path(config["output_root"])
        root.mkdir(parents=True, exist_ok=True)
        atomic_json(control_dir(root) / "PLAN.json", plan)
        return

    if args.cmd == "run":
        config = load_config(Path(args.config).expanduser())
        plan = make_plan(config)
        print_plan(plan)
        run_plan(config, plan)
        return

    if args.cmd == "monitor":
        monitor(Path(args.output_root), args.interval)
        return

    if args.cmd == "inspect":
        inspect_htmls([Path(x).expanduser() for x in args.html])
        return


if __name__ == "__main__":
    main()

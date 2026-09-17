#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ABRXOS CUTTER CONTROL PANEL V3
macOS local browser UI for ABRXOS_MULTI_HTML_CUTTER_V2.py

- Opens a browser tab automatically.
- All questions happen in the visual control panel.
- Finder is used to select HTMLs, vertical/horizontal masters and output folder.
- Live progress is shown in the same tab.
- No third-party Python packages required.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ENGINE_FILE = HERE / "ABRXOS_MULTI_HTML_CUTTER_V2.py"

if not ENGINE_FILE.exists():
    raise SystemExit(
        "No encuentro ABRXOS_MULTI_HTML_CUTTER_V2.py en la misma carpeta que este panel."
    )

sys.path.insert(0, str(HERE))
import ABRXOS_MULTI_HTML_CUTTER_V2 as engine  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def osa(lines: List[str], argv: Optional[List[str]] = None):
    if sys.platform != "darwin":
        return 127, "", "Este panel está diseñado para macOS."
    cmd = ["osascript"]
    for line in lines:
        cmd += ["-e", line]
    if argv:
        cmd += ["--", *argv]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def choose_htmls_native() -> List[Path]:
    rc, out, _ = osa([
        'set fs to choose file with prompt "Selecciona uno o varios HTML de contenido" with multiple selections allowed',
        'set o to ""',
        'repeat with f in fs',
        'set o to o & POSIX path of f & linefeed',
        'end repeat',
        'return o'
    ])
    if rc != 0 or not out:
        return []
    return [Path(x.strip()).expanduser() for x in out.splitlines() if x.strip()]


def choose_video_native(prompt: str) -> Optional[Path]:
    rc, out, _ = osa([
        'on run argv',
        'set f to choose file with prompt (item 1 of argv)',
        'return POSIX path of f',
        'end run'
    ], [prompt])
    if rc != 0 or not out:
        return None
    return Path(out).expanduser()


def choose_folder_native(prompt: str) -> Optional[Path]:
    rc, out, _ = osa([
        'on run argv',
        'set f to choose folder with prompt (item 1 of argv)',
        'return POSIX path of f',
        'end run'
    ], [prompt])
    if rc != 0 or not out:
        return None
    return Path(out).expanduser()


def open_in_finder(path: Path):
    if path.exists():
        subprocess.Popen(["open", str(path)])


class Session:
    def __init__(self):
        self.lock = threading.RLock()
        self.docs = []
        self.inventory: Dict[str, Dict[str, Any]] = {}
        self.masters: Dict[str, Dict[str, Optional[str]]] = {}
        self.output_parent: Optional[Path] = None
        self.output_root: Optional[Path] = None
        self.config: Optional[Dict[str, Any]] = None
        self.plan: Optional[Dict[str, Any]] = None
        self.render_thread: Optional[threading.Thread] = None
        self.render_error: Optional[str] = None
        self.render_finished = False
        self.created_at = datetime.now().isoformat(timespec="seconds")

    def is_rendering(self) -> bool:
        return bool(self.render_thread and self.render_thread.is_alive())

    def ensure_editable(self):
        if self.is_rendering():
            raise RuntimeError("Hay un render activo. Espera a que termine antes de cambiar la configuración.")

    def invalidate_plan(self):
        self.config = None
        self.plan = None
        self.output_root = None
        self.render_error = None
        self.render_finished = False

    def select_htmls(self):
        with self.lock:
            self.ensure_editable()
        paths = choose_htmls_native()
        if not paths:
            return False

        docs = []
        errors = []
        for p in paths:
            try:
                docs.append(engine.parse_html(p))
            except Exception as exc:
                errors.append(f"{p.name}: {exc}")

        if not docs:
            raise RuntimeError("Ningún HTML seleccionado pudo analizarse.\n" + "\n".join(errors))

        inventory = engine.build_source_inventory(docs)
        old = self.masters.copy()

        masters = {}
        for key in inventory:
            masters[key] = old.get(key, {"vertical": None, "horizontal": None})

        with self.lock:
            self.docs = docs
            self.inventory = inventory
            self.masters = masters
            self.invalidate_plan()

        return {"errors": errors}

    def select_master(self, key: str, orientation: str):
        if orientation not in {"vertical", "horizontal"}:
            raise ValueError("Orientación inválida.")
        with self.lock:
            self.ensure_editable()
            item = self.inventory.get(key)
            if not item:
                raise KeyError(f"Fuente no encontrada: {key}")

        label = f"{item['project_id']} · {item['label']} [{item['source_code']}]"
        p = choose_video_native(
            f"{label}\n\nMASTER {orientation.upper()}\nSelecciona el video fuente."
        )
        if p:
            with self.lock:
                self.masters[key][orientation] = str(p.resolve())
                self.invalidate_plan()
            return True
        return False

    def clear_master(self, key: str, orientation: str):
        with self.lock:
            self.ensure_editable()
            if key not in self.masters:
                raise KeyError(key)
            self.masters[key][orientation] = None
            self.invalidate_plan()

    def select_output(self):
        with self.lock:
            self.ensure_editable()
        p = choose_folder_native("Selecciona dónde crear la carpeta ABRXOS_EXPORT")
        if not p:
            return False
        with self.lock:
            self.output_parent = p.resolve()
            self.invalidate_plan()
        return True

    def build_plan(self):
        with self.lock:
            self.ensure_editable()
            if not self.docs:
                raise RuntimeError("Primero selecciona al menos un HTML.")
            if not self.output_parent:
                raise RuntimeError("Selecciona la carpeta de salida.")

            root = self.output_parent / ("ABRXOS_EXPORT_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
            config = {
                "schema_version": "abrxos.multi-html-cutter.v2",
                "version": engine.VERSION,
                "created_at": engine.now_iso(),
                "htmls": [d.path for d in self.docs],
                "masters": self.masters,
                "output_root": str(root.resolve()),
                "render_profile": engine.RENDER_PROFILE_ID,
                "notes": {
                    "created_by": "ABRXOS_CUTTER_CONTROL_PANEL_V3",
                    "one_piece_one_video": True,
                    "hook_development_close_are_internal_parts": True,
                    "phase_order": ["intros", "verticals", "horizontals"],
                    "skip_full_episode": True,
                },
            }

        plan = engine.make_plan(config)
        root.mkdir(parents=True, exist_ok=True)
        ctl = engine.control_dir(root)
        ctl.mkdir(parents=True, exist_ok=True)
        engine.atomic_json(ctl / "CONFIG.json", config)
        engine.atomic_json(ctl / "PLAN.json", plan)

        with self.lock:
            self.output_root = root
            self.config = config
            self.plan = plan
            self.render_error = None
            self.render_finished = False
        return True

    def start_render(self):
        with self.lock:
            if self.is_rendering():
                raise RuntimeError("El render ya está en marcha.")
            if not self.config or not self.plan or not self.output_root:
                raise RuntimeError("Primero crea el plan de corte.")
            self.render_error = None
            self.render_finished = False
            config = dict(self.config)
            plan = dict(self.plan)

        def worker():
            try:
                engine.run_plan(config, plan)
            except Exception:
                with self.lock:
                    self.render_error = traceback.format_exc()
            finally:
                with self.lock:
                    self.render_finished = True

        t = threading.Thread(target=worker, name="ABRXOS_RENDER", daemon=True)
        with self.lock:
            self.render_thread = t
        t.start()

    def read_state(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            root = self.output_root
        if not root:
            return None
        a, b = engine.state_paths(root)
        path = a if a.exists() else b if b.exists() else None
        if not path:
            return None
        try:
            return json.loads(engine.read_text(path))
        except Exception:
            return None

    def progress_payload(self) -> Dict[str, Any]:
        state = self.read_state()
        with self.lock:
            plan = self.plan
            rendering = self.is_rendering()
            error = self.render_error
            finished = self.render_finished
            root = str(self.output_root) if self.output_root else None

        if state:
            summary = engine.state_summary(state)
            items = list(state.get("items", {}).values())
            done = [x for x in items if x.get("status") in {"DONE", "SKIPPED_VALID"}]
            failed = [x for x in items if x.get("status") == "FAILED"]
            pending = [x for x in items if x.get("status") not in {"DONE", "SKIPPED_VALID", "FAILED"}]
            current_id = state.get("current_job_id")
            current = state.get("items", {}).get(current_id) if current_id else None
            return {
                "available": True,
                "rendering": rendering,
                "finished": finished,
                "error": error,
                "root": root,
                "updated_at": state.get("updated_at"),
                "summary": summary,
                "current": current,
                "recent_done": done[-8:][::-1],
                "recent_failed": failed[-8:][::-1],
                "pending_count": len(pending),
            }

        total = plan.get("job_count", 0) if plan else 0
        return {
            "available": bool(plan),
            "rendering": rendering,
            "finished": finished,
            "error": error,
            "root": root,
            "updated_at": None,
            "summary": {
                "total": total,
                "done": 0,
                "failed": 0,
                "processing": [],
                "pct": 0,
                "phases": {
                    "01_INTROS": {"done": 0, "total": plan.get("counts", {}).get("01_INTROS", 0) if plan else 0, "pct": 0},
                    "02_VERTICALES": {"done": 0, "total": plan.get("counts", {}).get("02_VERTICALES", 0) if plan else 0, "pct": 0},
                    "03_HORIZONTALES": {"done": 0, "total": plan.get("counts", {}).get("03_HORIZONTALES", 0) if plan else 0, "pct": 0},
                },
            },
            "current": None,
            "recent_done": [],
            "recent_failed": [],
            "pending_count": total,
        }

    def public_payload(self) -> Dict[str, Any]:
        with self.lock:
            htmls = [{
                "path": d.path,
                "name": Path(d.path).name,
                "title": d.title,
                "script_id": d.script_id,
                "pieces": len(d.pieces),
                "project": d.canonical_project_id,
            } for d in self.docs]

            sources = []
            for key, item in self.inventory.items():
                m = self.masters.get(key, {})
                sources.append({
                    "key": key,
                    "project_id": item["project_id"],
                    "source_code": item["source_code"],
                    "label": item["label"],
                    "piece_count": item["piece_count"],
                    "htmls": sorted({Path(x).name for x in item["htmls"]}),
                    "vertical": m.get("vertical"),
                    "horizontal": m.get("horizontal"),
                })

            plan_summary = None
            if self.plan:
                plan_summary = {
                    "total": self.plan["job_count"],
                    "counts": self.plan.get("counts", {}),
                    "skipped": len(self.plan.get("skipped", [])),
                    "output_root": self.plan.get("output_root"),
                }

            return {
                "version": "3.0.0",
                "htmls": htmls,
                "sources": sources,
                "output_parent": str(self.output_parent) if self.output_parent else None,
                "output_root": str(self.output_root) if self.output_root else None,
                "plan": plan_summary,
                "rendering": self.is_rendering(),
                "render_finished": self.render_finished,
            }


SESSION = Session()


HTML = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABRXOS Cutter</title>
<style>
:root{
  color-scheme:dark;
  --bg:#0c0d10;--panel:#15171b;--panel2:#1b1e24;--line:#30343d;
  --text:#f5f5f7;--muted:#9ca3af;--accent:#9d6cff;--accent2:#7651d9;
  --good:#63d18c;--warn:#e7b65a;--bad:#ff6b78;--blue:#60a5fa;
  font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text)}
button{font:inherit;color:inherit;cursor:pointer;border:1px solid var(--line);background:#20232a;border-radius:10px;min-height:42px;padding:9px 13px}
button:hover{background:#292d35}button:disabled{opacity:.42;cursor:not-allowed}
button.primary{background:var(--accent2);border-color:#9d7cff}
button.ghost{background:transparent}
button.danger{color:#ffc2c7}
.wrap{max-width:1300px;margin:0 auto;padding:24px}
.top{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:20px}
.brand{display:flex;gap:12px;align-items:center}.mark{width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,#8b5cff,#4c2da2);display:grid;place-items:center;font-weight:850}
.brand h1{font-size:20px;margin:0}.brand p{margin:2px 0 0;color:var(--muted);font-size:12px}
.grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(340px,.75fr);gap:18px;align-items:start}
.stack{display:grid;gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:17px}
.card h2{font-size:15px;margin:0}.head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:14px}
.step{display:inline-flex;align-items:center;justify-content:center;width:25px;height:25px;border-radius:50%;background:#2a2438;color:#d9c6ff;font-size:11px;font-weight:750;margin-right:8px}
.note{font-size:12px;color:var(--muted);margin:8px 0 0}
.empty{border:1px dashed #3d424d;border-radius:11px;padding:18px;color:var(--muted);text-align:center}
.html-row,.source{background:var(--panel2);border:1px solid #292d35;border-radius:11px;padding:12px;margin-top:8px}
.html-row strong,.source strong{display:block;font-size:13px}.sub{font-size:11px;color:var(--muted);overflow-wrap:anywhere}
.source-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.badge{font-size:10px;padding:3px 7px;border-radius:999px;background:#252936;color:#c5cad3;white-space:nowrap}
.master-grid{display:grid;grid-template-columns:92px minmax(0,1fr) auto auto;gap:7px;align-items:center;margin-top:10px}
.master-grid .kind{font-size:11px;color:#c5cad3}
.file{font:11px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aeb5c2;background:#101216;border:1px solid #2a2e36;border-radius:7px;padding:8px}
.small{min-height:34px;padding:5px 8px;font-size:11px}
.output{display:flex;gap:8px;align-items:center}.output .file{flex:1}
.plan-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.metric{border:1px solid #2e323b;border-radius:10px;padding:11px;background:#111318}
.metric b{font-size:21px;display:block}.metric span{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}
.progress-card{position:sticky;top:18px}
.p-title{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.status-pill{font-size:10px;padding:4px 8px;border-radius:999px;background:#272b32;color:#b8bec9}
.status-pill.live{background:#173a2a;color:#9ff0bd}
.status-pill.err{background:#402127;color:#ffb3ba}
.bigpct{font-size:42px;font-weight:760;letter-spacing:-2px;margin:16px 0 4px}
.bar{height:10px;background:#242830;border-radius:999px;overflow:hidden}.bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#7751d8,#a67cff);transition:width .3s}
.phase{margin-top:14px}.phase-line{display:flex;justify-content:space-between;font-size:11px;margin-bottom:5px;color:#c6cbd4}.phase .bar{height:7px}
.current{margin-top:16px;padding:13px;border:1px solid #3b3449;background:#1d1924;border-radius:11px}
.current .eyebrow{font-size:9px;color:#a995c9;text-transform:uppercase;letter-spacing:1px}.current h3{font-size:14px;margin:5px 0}.current p{font-size:11px;color:#c4bacf;margin:0}
.lists{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}
.mini{border-top:1px solid #292d35;padding-top:10px}.mini h4{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.7px;margin:0 0 7px}
.mini ul{list-style:none;padding:0;margin:0;display:grid;gap:4px}.mini li{font-size:10px;color:#bac0ca;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.errorbox{white-space:pre-wrap;max-height:180px;overflow:auto;font:10px/1.4 ui-monospace,monospace;color:#ffb3ba;background:#1f1115;border:1px solid #532630;border-radius:9px;padding:10px;margin-top:12px}
.actions{display:flex;gap:8px;flex-wrap:wrap}
.toast{position:fixed;right:20px;bottom:20px;max-width:430px;background:#252831;border:1px solid #4d5360;border-radius:11px;padding:11px 14px;display:none;box-shadow:0 16px 50px #0008}
.toast.show{display:block}
@media(max-width:900px){.grid{grid-template-columns:1fr}.progress-card{position:static}.plan-grid{grid-template-columns:1fr 1fr}}
@media(max-width:560px){.wrap{padding:12px}.top{align-items:flex-start}.master-grid{grid-template-columns:1fr 1fr}.master-grid .kind,.master-grid .file{grid-column:1/-1}.lists{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand"><div class="mark">AB</div><div><h1>ABRXOS Cutter</h1><p>Control Panel · HTML → masters → cortes</p></div></div>
    <button id="openOut" class="ghost" disabled>Abrir salida en Finder</button>
  </header>

  <div class="grid">
    <div class="stack">
      <section class="card">
        <div class="head"><h2><span class="step">1</span>HTML de contenido</h2><button id="pickHtml" class="primary">Seleccionar HTML</button></div>
        <div id="htmlList" class="empty">Selecciona uno o varios HTML. El programa detectará automáticamente sus fuentes.</div>
      </section>

      <section class="card">
        <div class="head"><h2><span class="step">2</span>Masters por fuente</h2><span class="badge">V y H son opcionales</span></div>
        <div id="sources" class="empty">Primero selecciona los HTML.</div>
        <p class="note">Si dejas Vertical u Horizontal vacío, esa orientación simplemente no se produce. Un HTML puede contener varias fuentes diferentes.</p>
      </section>

      <section class="card">
        <div class="head"><h2><span class="step">3</span>Carpeta de salida</h2><button id="pickOutput">Seleccionar carpeta</button></div>
        <div class="output"><div id="outputPath" class="file">Sin seleccionar</div></div>
      </section>

      <section class="card">
        <div class="head"><h2><span class="step">4</span>Plan de corte</h2><button id="buildPlan">Crear / actualizar plan</button></div>
        <div id="planArea" class="empty">El plan te mostrará cuántos MP4 finales saldrán antes de empezar.</div>
      </section>

      <section class="card">
        <div class="head"><h2><span class="step">5</span>Producción</h2></div>
        <div class="actions">
          <button id="startRender" class="primary" disabled>Comenzar cortes</button>
          <span id="productionNote" class="note">Crea el plan primero.</span>
        </div>
      </section>
    </div>

    <aside class="card progress-card">
      <div class="p-title">
        <div><h2>Progreso en vivo</h2><div id="updated" class="note">Esperando plan…</div></div>
        <span id="livePill" class="status-pill">En espera</span>
      </div>

      <div id="bigPct" class="bigpct">0%</div>
      <div class="bar"><i id="generalBar"></i></div>
      <div id="generalMeta" class="note">0 / 0 listos</div>

      <div class="phase">
        <div class="phase-line"><span>INTROS</span><span id="introMeta">0/0</span></div>
        <div class="bar"><i id="introBar"></i></div>
      </div>
      <div class="phase">
        <div class="phase-line"><span>VERTICALES</span><span id="verticalMeta">0/0</span></div>
        <div class="bar"><i id="verticalBar"></i></div>
      </div>
      <div class="phase">
        <div class="phase-line"><span>HORIZONTALES</span><span id="horizontalMeta">0/0</span></div>
        <div class="bar"><i id="horizontalBar"></i></div>
      </div>

      <div class="current">
        <div class="eyebrow">Video actual</div>
        <h3 id="currentTitle">—</h3>
        <p id="currentDetail">Todavía no hay un render activo.</p>
      </div>

      <div class="lists">
        <div class="mini"><h4>Últimos terminados</h4><ul id="doneList"><li>—</li></ul></div>
        <div class="mini"><h4>Errores</h4><ul id="failList"><li>—</li></ul></div>
      </div>
      <div id="errorBox" class="errorbox" hidden></div>
    </aside>
  </div>
</div>
<div id="toast" class="toast" role="status"></div>

<script>
const $ = s => document.querySelector(s);
let session = null;

function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function baseName(p){return p ? p.split('/').filter(Boolean).pop() : '—';}
function toast(msg){const t=$('#toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),3500);}
async function api(path, method='GET', body=null){
  const opt={method,headers:{}};
  if(body!==null){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body);}
  const r=await fetch(path,opt);
  const j=await r.json().catch(()=>({ok:false,error:'Respuesta inválida'}));
  if(!r.ok || j.ok===false) throw new Error(j.error||('HTTP '+r.status));
  return j;
}
function disableWhileRendering(){
  const r=session?.rendering;
  ['#pickHtml','#pickOutput','#buildPlan'].forEach(s=>$(s).disabled=!!r);
  document.querySelectorAll('[data-master],[data-clear]').forEach(b=>b.disabled=!!r);
}
function renderSession(){
  const h=$('#htmlList');
  if(!session.htmls.length) h.innerHTML='<div class="empty">Selecciona uno o varios HTML. El programa detectará automáticamente sus fuentes.</div>';
  else h.innerHTML=session.htmls.map(x=>`<div class="html-row"><strong>${esc(x.name)}</strong><div class="sub">${esc(x.project)} · ${x.pieces} piezas · #${esc(x.script_id)}</div></div>`).join('');

  const s=$('#sources');
  if(!session.sources.length) s.innerHTML='<div class="empty">Primero selecciona los HTML.</div>';
  else s.innerHTML=session.sources.map(x=>`
    <div class="source">
      <div class="source-head">
        <div><strong>${esc(x.project_id)} · ${esc(x.label)}</strong><div class="sub">${esc(x.source_code)} · ${x.piece_count} piezas · ${esc(x.htmls.join(', '))}</div></div>
        <span class="badge">${x.piece_count} piezas</span>
      </div>
      <div class="master-grid">
        <div class="kind">VERTICAL</div>
        <div class="file" title="${esc(x.vertical||'')}">${esc(baseName(x.vertical)||'—')}</div>
        <button class="small" data-master="${esc(x.key)}" data-orientation="vertical">Seleccionar</button>
        <button class="small danger" data-clear="${esc(x.key)}" data-orientation="vertical">Omitir</button>

        <div class="kind">HORIZONTAL</div>
        <div class="file" title="${esc(x.horizontal||'')}">${esc(baseName(x.horizontal)||'—')}</div>
        <button class="small" data-master="${esc(x.key)}" data-orientation="horizontal">Seleccionar</button>
        <button class="small danger" data-clear="${esc(x.key)}" data-orientation="horizontal">Omitir</button>
      </div>
    </div>`).join('');

  $('#outputPath').textContent=session.output_parent||'Sin seleccionar';

  const p=$('#planArea');
  if(!session.plan) p.innerHTML='<div class="empty">El plan te mostrará cuántos MP4 finales saldrán antes de empezar.</div>';
  else {
    const c=session.plan.counts||{};
    p.innerHTML=`<div class="plan-grid">
      <div class="metric"><b>${session.plan.total}</b><span>MP4 finales</span></div>
      <div class="metric"><b>${c['01_INTROS']||0}</b><span>Intros</span></div>
      <div class="metric"><b>${c['02_VERTICALES']||0}</b><span>Verticales</span></div>
      <div class="metric"><b>${c['03_HORIZONTALES']||0}</b><span>Horizontales</span></div>
    </div><p class="note">${session.plan.skipped} piezas omitidas (carruseles, estáticos, episodio completo, sin master compatible o sin rango válido).</p>`;
  }

  $('#startRender').disabled=!session.plan || session.rendering;
  $('#productionNote').textContent=session.rendering?'Producción en marcha. Puedes dejar esta pestaña abierta.':session.plan?'Listo para comenzar.':'Crea el plan primero.';
  $('#openOut').disabled=!session.output_root;
  disableWhileRendering();
  bindDynamic();
}
function bindDynamic(){
  document.querySelectorAll('[data-master]').forEach(b=>b.addEventListener('click',async()=>{
    try{await api('/api/select_master','POST',{key:b.dataset.master,orientation:b.dataset.orientation});await refreshSession();}
    catch(e){toast(e.message);}
  }));
  document.querySelectorAll('[data-clear]').forEach(b=>b.addEventListener('click',async()=>{
    try{await api('/api/clear_master','POST',{key:b.dataset.clear,orientation:b.dataset.orientation});await refreshSession();}
    catch(e){toast(e.message);}
  }));
}
async function refreshSession(){
  const r=await api('/api/session');session=r.session;renderSession();
}
function setBar(id,pct){$(id).style.width=Math.max(0,Math.min(100,pct||0))+'%';}
function fillList(id, rows){
  const el=$(id);
  if(!rows?.length){el.innerHTML='<li>—</li>';return;}
  el.innerHTML=rows.map(x=>`<li title="${esc(x.title)}">${esc(x.piece_id)} · ${esc((x.orientation||'').toUpperCase())}</li>`).join('');
}
async function refreshProgress(){
  try{
    const r=await api('/api/progress');
    const p=r.progress, s=p.summary||{}, phases=s.phases||{};
    const pct=Number(s.pct||0);
    $('#bigPct').textContent=pct.toFixed(0)+'%';
    setBar('#generalBar',pct);
    $('#generalMeta').textContent=`${s.done||0} / ${s.total||0} listos · ${s.failed||0} fallidos · ${p.pending_count||0} pendientes`;
    const map=[['01_INTROS','#introBar','#introMeta'],['02_VERTICALES','#verticalBar','#verticalMeta'],['03_HORIZONTALES','#horizontalBar','#horizontalMeta']];
    for(const [k,b,m] of map){const q=phases[k]||{pct:0,done:0,total:0};setBar(b,q.pct);$(m).textContent=`${q.done}/${q.total}`;}
    $('#updated').textContent=p.updated_at?'Actualizado '+p.updated_at:'Esperando actividad…';

    const pill=$('#livePill');
    pill.className='status-pill';
    if(p.error){pill.classList.add('err');pill.textContent='Error';}
    else if(p.rendering){pill.classList.add('live');pill.textContent='Procesando';}
    else if(p.finished && s.total && s.done===s.total){pill.classList.add('live');pill.textContent='Terminado';}
    else pill.textContent='En espera';

    if(p.current){
      $('#currentTitle').textContent=`${p.current.piece_id} · ${(p.current.orientation||'').toUpperCase()} · ${p.current.title}`;
      $('#currentDetail').textContent=`${p.current.status} · ${(p.current.progress||0).toFixed(1)}% · ${p.current.detail||''}`;
    }else{
      $('#currentTitle').textContent='—';
      $('#currentDetail').textContent=p.rendering?'Preparando siguiente video…':'Todavía no hay un render activo.';
    }
    fillList('#doneList',p.recent_done);
    fillList('#failList',p.recent_failed);
    const eb=$('#errorBox');
    if(p.error){eb.hidden=false;eb.textContent=p.error;} else {eb.hidden=true;eb.textContent='';}
    if(session && session.rendering!==p.rendering){await refreshSession();}
  }catch(e){console.error(e);}
}
$('#pickHtml').addEventListener('click',async()=>{try{await api('/api/select_htmls','POST',{});await refreshSession();toast('HTML analizados.');}catch(e){toast(e.message);}});
$('#pickOutput').addEventListener('click',async()=>{try{await api('/api/select_output','POST',{});await refreshSession();}catch(e){toast(e.message);}});
$('#buildPlan').addEventListener('click',async()=>{try{await api('/api/build_plan','POST',{});await refreshSession();await refreshProgress();toast('Plan creado. Revisa los conteos antes de comenzar.');}catch(e){toast(e.message);}});
$('#startRender').addEventListener('click',async()=>{if(!confirm('¿Comenzar los cortes ahora? El orden será: intros → verticales → horizontales.'))return;try{await api('/api/start','POST',{});await refreshSession();await refreshProgress();}catch(e){toast(e.message);}});
$('#openOut').addEventListener('click',async()=>{try{await api('/api/open_output','POST',{});}catch(e){toast(e.message);}});

refreshSession().then(refreshProgress);
setInterval(refreshProgress,1000);
setInterval(refreshSession,4000);
</script>

<!-- ABRXS_PROCESS_CONTROL_WIDGET_V311 -->
<style>
#abrxs-process-control{position:fixed;right:18px;bottom:18px;z-index:2147483000;width:300px;background:rgba(16,18,24,.96);color:#f5f7fb;border:1px solid rgba(255,255,255,.14);border-radius:16px;box-shadow:0 18px 60px rgba(0,0,0,.34);font:13px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:14px}
#abrxs-process-control .abrxs-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
#abrxs-process-control .abrxs-title{font-weight:700;font-size:14px}
#abrxs-process-control .abrxs-state{font-weight:700;font-size:11px;padding:5px 8px;border-radius:999px;background:#2a2e39}
#abrxs-process-control .abrxs-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
#abrxs-process-control button{border:0;border-radius:10px;padding:9px 10px;cursor:pointer;font-weight:650;background:#2a2e39;color:#fff}
#abrxs-process-control button.abrxs-danger{background:#8e2f35}
#abrxs-process-control button.abrxs-close{grid-column:1 / -1;background:#383d4a}
#abrxs-process-details{display:none;max-height:180px;overflow:auto;margin-top:10px;padding-top:9px;border-top:1px solid rgba(255,255,255,.10);font:11px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;color:#cbd1dc}
#abrxs-close-modal{display:none;position:fixed;inset:0;z-index:2147483646;background:rgba(0,0,0,.48);align-items:center;justify-content:center;padding:24px}
#abrxs-close-modal .abrxs-modal-card{width:min(460px,100%);background:#171a22;color:#fff;border-radius:18px;padding:20px;box-shadow:0 20px 70px rgba(0,0,0,.5)}
#abrxs-close-modal .abrxs-modal-actions{display:grid;gap:9px;margin-top:16px}
#abrxs-close-modal button{border:0;border-radius:11px;padding:11px 12px;font-weight:700;cursor:pointer}
</style>
<div id="abrxs-process-control">
  <div class="abrxs-row"><div class="abrxs-title">ABRXS Cutter · Procesos</div><div id="abrxs-process-state" class="abrxs-state">INACTIVO</div></div>
  <div id="abrxs-process-summary" style="margin-top:7px;color:#aeb6c5">Sin render activo.</div>
  <div class="abrxs-actions">
    <button id="abrxs-view-processes" type="button">Ver procesos</button>
    <button id="abrxs-cancel-render" type="button" class="abrxs-danger">Cancelar render</button>
    <button id="abrxs-close-cutter" type="button" class="abrxs-close">Cerrar Cutter…</button>
  </div>
  <div id="abrxs-process-details"></div>
</div>
<div id="abrxs-close-modal">
  <div class="abrxs-modal-card">
    <div style="font-size:17px;font-weight:750">Cerrar ABRXS Cutter</div>
    <div id="abrxs-close-copy" style="margin-top:8px;color:#bdc4d1">Elige qué hacer con el render actual.</div>
    <div class="abrxs-modal-actions">
      <button id="abrxs-close-cancel" style="background:#8e2f35;color:#fff">Cancelar render y salir</button>
      <button id="abrxs-close-background" style="background:#303746;color:#fff">Dejar render en segundo plano y salir</button>
      <button id="abrxs-close-back" style="background:#eceff4;color:#16181d">Volver</button>
    </div>
  </div>
</div>
<script>
(()=>{
  const API='http://127.0.0.1:17831';
  const $=s=>document.querySelector(s);
  let last={active:false,state:'INACTIVO',processes:[]};
  let detailsOpen=false;
  const labels={INACTIVE:'INACTIVO',RENDERING:'RENDERIZANDO',CANCELING:'CANCELANDO',ERROR:'ERROR'};
  function render(s){
    last=s||last;
    $('#abrxs-process-state').textContent=labels[last.state]||last.state||'INACTIVO';
    $('#abrxs-process-summary').textContent=last.active?`Render activo · PID ${last.renderPids.join(', ')}`:'Sin render activo.';
    $('#abrxs-cancel-render').disabled=!last.active;
    const NL=String.fromCharCode(10);
    const lines=(last.processes||[]).map(p=>`PID ${p.pid} · ${p.kind} · ${p.elapsed}${NL}${p.command}`);
    $('#abrxs-process-details').textContent=lines.length?lines.join(NL+NL):'No hay procesos de render.';
    $('#abrxs-process-details').style.display=detailsOpen?'block':'none';
  }
  async function status(){
    try{const r=await fetch(API+'/status',{cache:'no-store'});render(await r.json());}
    catch(e){render({active:false,state:'ERROR',renderPids:[],processes:[],error:String(e)});}
  }
  async function post(path,body={}){const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json();}
  $('#abrxs-view-processes').addEventListener('click',()=>{detailsOpen=!detailsOpen;render(last);if(detailsOpen)status();});
  $('#abrxs-cancel-render').addEventListener('click',async()=>{if(!last.active)return;if(!confirm('¿Cancelar el render activo y sus procesos FFmpeg?'))return;render({...last,state:'CANCELING'});await post('/cancel');await status();});
  $('#abrxs-close-cutter').addEventListener('click',()=>{const m=$('#abrxs-close-modal');$('#abrxs-close-copy').textContent=last.active?'Hay un render activo. ¿Qué quieres hacer?':'No hay render activo. Puedes cerrar el panel.';m.style.display='flex';});
  $('#abrxs-close-back').addEventListener('click',()=>{$('#abrxs-close-modal').style.display='none';});
  $('#abrxs-close-cancel').addEventListener('click',async()=>{await post('/shutdown',{cancelRender:true});setTimeout(()=>window.close(),180);});
  $('#abrxs-close-background').addEventListener('click',async()=>{await post('/shutdown',{cancelRender:false});setTimeout(()=>window.close(),180);});
  window.addEventListener('beforeunload',e=>{if(last.active){e.preventDefault();e.returnValue='';}});
  status();setInterval(status,1500);
})();
</script>

</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "ABRXOSPanel/3.0"

    def log_message(self, fmt, *args):
        return

    def send_json(self, obj: Any, status: int = 200):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_html(self, text: str):
        raw = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def json_body(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length", "0") or "0")
        if not n:
            return {}
        raw = self.rfile.read(n)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/":
                self.send_html(HTML)
                return
            if path == "/api/session":
                self.send_json({"ok": True, "session": SESSION.public_payload()})
                return
            if path == "/api/progress":
                self.send_json({"ok": True, "progress": SESSION.progress_payload()})
                return
            self.send_json({"ok": False, "error": "Ruta no encontrada"}, 404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self.json_body()

            if path == "/api/select_htmls":
                result = SESSION.select_htmls()
                self.send_json({"ok": True, "result": result})
                return

            if path == "/api/select_master":
                ok = SESSION.select_master(str(body.get("key", "")), str(body.get("orientation", "")))
                self.send_json({"ok": True, "selected": ok})
                return

            if path == "/api/clear_master":
                SESSION.clear_master(str(body.get("key", "")), str(body.get("orientation", "")))
                self.send_json({"ok": True})
                return

            if path == "/api/select_output":
                ok = SESSION.select_output()
                self.send_json({"ok": True, "selected": ok})
                return

            if path == "/api/build_plan":
                SESSION.build_plan()
                self.send_json({"ok": True})
                return

            if path == "/api/start":
                SESSION.start_render()
                self.send_json({"ok": True})
                return

            if path == "/api/open_output":
                if not SESSION.output_root:
                    raise RuntimeError("Todavía no existe una carpeta de salida.")
                open_in_finder(SESSION.output_root)
                self.send_json({"ok": True})
                return

            self.send_json({"ok": False, "error": "Ruta no encontrada"}, 404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 409)


def find_port(start: int = DEFAULT_PORT) -> int:
    import socket
    for port in range(start, start + 40):
        s = socket.socket()
        try:
            s.bind((HOST, port))
            s.close()
            return port
        except OSError:
            s.close()
    raise RuntimeError("No encontré un puerto local libre.")


def main():
    if sys.platform != "darwin":
        raise SystemExit("ABRXOS Cutter Control Panel V3 está diseñado para macOS.")

    port = find_port()
    url = f"http://{HOST}:{port}/"
    server = ThreadingHTTPServer((HOST, port), Handler)

    def open_ui():
        time.sleep(0.45)
        try:
            subprocess.Popen(["open", url])
        except Exception:
            webbrowser.open(url)

    threading.Thread(target=open_ui, daemon=True).start()

    print(f"ABRXOS Cutter Control Panel V3 · {url}")
    print("El panel visual ya se abrió en el navegador.")

    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# ABRXS_PROCESS_CONTROL_V311_HOOK
from ABRXOS_CUTTER_PROCESS_CONTROL_V311 import start_server_once as _abrxs_start_process_control
_abrxs_start_process_control()

if __name__ == "__main__":
    main()

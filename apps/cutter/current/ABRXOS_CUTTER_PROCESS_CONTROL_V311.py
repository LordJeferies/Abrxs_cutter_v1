#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

SERVICE_NAME = "abrxs-cutter-process-control"
VERSION = "3.1.1"
PORT = 17831
ENGINE_BASENAME = "ABRXOS_MULTI_HTML_CUTTER_V2.py"
CONTROL_BASENAME = "ABRXOS_CUTTER_CONTROL_PANEL_V3.py"
RUNTIME_DIR = Path.home() / ".abrxos" / "cutter" / "runtime"

_STATE_LOCK = threading.Lock()
_STATE = "INACTIVE"
_SERVER_STARTED = False


@dataclass(frozen=True)
class ProcessRow:
    pid: int
    ppid: int
    pgid: int
    elapsed: str
    command: str
    argv: tuple[str, ...]
    mode: str = ""


def _argv(command: str) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(command))
    except ValueError:
        return tuple(command.split())


def parse_process_table(text: str) -> List[ProcessRow]:
    rows: List[ProcessRow] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        try:
            pid, ppid, pgid = (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            continue
        elapsed, command = parts[3], parts[4]
        rows.append(ProcessRow(pid, ppid, pgid, elapsed, command, _argv(command)))
    return rows


def process_table() -> List[ProcessRow]:
    proc = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,pgid=,etime=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_process_table(proc.stdout)


def _script_index(argv: Sequence[str], basename: str) -> Optional[int]:
    for i, token in enumerate(argv):
        if Path(token).name == basename:
            return i
    return None


def _mode_after_script(argv: Sequence[str], script_index: int) -> str:
    for token in argv[script_index + 1 :]:
        if token.startswith("-"):
            continue
        return token
    return ""


def _is_real_engine(row: ProcessRow) -> tuple[bool, str]:
    idx = _script_index(row.argv, ENGINE_BASENAME)
    if idx is None:
        return False, ""
    # A string inside python -c/awk/grep is not an executable script token.
    if idx > 0 and row.argv[idx - 1] == "-c":
        return False, ""
    if idx > 0:
        launcher = Path(row.argv[idx - 1]).name.lower()
        if not ("python" in launcher or launcher in {"env", "uv", "python"}):
            # Direct executable script is allowed only when it is argv[0].
            return False, ""
    mode = _mode_after_script(row.argv, idx)
    if mode == "run":
        return True, mode
    if mode == "setup" and "--no-run" not in row.argv[idx + 1 :]:
        return True, mode
    return False, mode


def find_render_processes(rows: Sequence[ProcessRow]) -> List[ProcessRow]:
    out: List[ProcessRow] = []
    for row in rows:
        ok, mode = _is_real_engine(row)
        if ok:
            out.append(ProcessRow(row.pid, row.ppid, row.pgid, row.elapsed, row.command, row.argv, mode))
    return sorted(out, key=lambda r: r.pid)



def find_control_panels(rows: Sequence[ProcessRow]) -> List[ProcessRow]:
    out: List[ProcessRow] = []
    for row in rows:
        idx = _script_index(row.argv, CONTROL_BASENAME)
        if idx is None:
            continue
        if idx > 0 and row.argv[idx - 1] == "-c":
            continue
        if idx > 0:
            launcher = Path(row.argv[idx - 1]).name.lower()
            if not ("python" in launcher or launcher in {"env", "uv", "python"}):
                continue
        out.append(row)
    return sorted(out, key=lambda r: r.pid)


def descendant_pids(rows: Sequence[ProcessRow], roots: Set[int]) -> Set[int]:
    result = set(roots)
    changed = True
    while changed:
        changed = False
        for row in rows:
            if row.ppid in result and row.pid not in result:
                result.add(row.pid)
                changed = True
    return result


def status_payload(rows: Optional[Sequence[ProcessRow]] = None) -> dict:
    global _STATE
    try:
        rows = list(rows) if rows is not None else process_table()
        renders = find_render_processes(rows)
        roots = {p.pid for p in renders}
        tree = descendant_pids(rows, roots)
        child_pids = sorted(tree - roots)
        with _STATE_LOCK:
            state = _STATE
        if state not in {"CANCELING", "ERROR"}:
            state = "RENDERING" if roots else "INACTIVE"
        by_pid = {p.pid: p for p in rows}
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "version": VERSION,
            "active": bool(roots),
            "state": state,
            "renderPids": sorted(roots),
            "childPids": child_pids,
            "processes": [
                {
                    "pid": pid,
                    "ppid": by_pid[pid].ppid,
                    "elapsed": by_pid[pid].elapsed,
                    "kind": "render" if pid in roots else ("ffmpeg" if "ffmpeg" in Path(by_pid[pid].argv[0]).name.lower() else "child"),
                    "command": by_pid[pid].command,
                }
                for pid in sorted(tree)
                if pid in by_pid
            ],
        }
    except Exception as exc:
        with _STATE_LOCK:
            _STATE = "ERROR"
        return {
            "ok": False,
            "service": SERVICE_NAME,
            "version": VERSION,
            "active": False,
            "state": "ERROR",
            "error": str(exc),
            "renderPids": [],
            "childPids": [],
            "processes": [],
        }


def register_current_render() -> None:
    argv = tuple(sys.argv)
    row = ProcessRow(os.getpid(), os.getppid(), os.getpgrp(), "00:00", " ".join(shlex.quote(x) for x in argv), argv)
    ok, mode = _is_real_engine(row)
    if not ok:
        return
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNTIME_DIR / f"render_{os.getpid()}.json"
    payload = {"pid": os.getpid(), "ppid": os.getppid(), "mode": mode, "startedAt": time.time(), "argv": list(argv)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def cleanup() -> None:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    import atexit
    atexit.register(cleanup)


def stop_control_panels(timeout: float = 2.0) -> dict:
    rows = process_table()
    panels = [p for p in find_control_panels(rows) if p.pid != os.getpid()]
    pids = [p.pid for p in panels]
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.time() + timeout
    survivors = [pid for pid in pids if _alive(pid)]
    while survivors and time.time() < deadline:
        time.sleep(0.1)
        survivors = [pid for pid in survivors if _alive(pid)]
    return {"ok": True, "stopped": [pid for pid in pids if pid not in survivors], "survivors": survivors}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def cancel_all(timeout: float = 5.0) -> dict:
    global _STATE
    rows = process_table()
    renders = find_render_processes(rows)
    roots = {p.pid for p in renders}
    if not roots:
        return {"ok": True, "cancelled": [], "killed": [], "message": "No hay renders activos"}
    tree = descendant_pids(rows, roots)
    with _STATE_LOCK:
        _STATE = "CANCELING"
    cancelled: List[int] = []
    killed: List[int] = []
    # Children first (ffmpeg), then engine roots.
    order = sorted(tree - roots, reverse=True) + sorted(roots, reverse=True)
    for pid in order:
        try:
            os.kill(pid, signal.SIGTERM)
            cancelled.append(pid)
        except ProcessLookupError:
            pass
        except PermissionError:
            pass
    deadline = time.time() + timeout
    survivors = [pid for pid in order if _alive(pid)]
    while survivors and time.time() < deadline:
        time.sleep(0.1)
        survivors = [pid for pid in survivors if _alive(pid)]
    for pid in survivors:
        try:
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
        except (ProcessLookupError, PermissionError):
            pass
    with _STATE_LOCK:
        _STATE = "INACTIVE"
    return {"ok": True, "cancelled": cancelled, "killed": killed, "renderPids": sorted(roots)}


class _Handler(BaseHTTPRequestHandler):
    server_version = "ABRXSCutterProcessControl/3.1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def _headers(self, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, payload: dict, code: int = 200) -> None:
        self._headers(code)
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self) -> None:
        self._headers(204)

    def do_GET(self) -> None:
        if self.path.rstrip("/") in {"", "/status"}:
            self._json(status_payload())
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path == "/cancel":
            self._json(cancel_all())
            return
        if self.path == "/shutdown":
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            result = cancel_all() if bool(data.get("cancelRender")) else {"ok": True, "message": "render remains in background"}
            self._json(result)
            threading.Timer(0.25, lambda: os._exit(0)).start()
            return
        self._json({"ok": False, "error": "not found"}, 404)


def _server_healthy(port: int = PORT) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=0.35) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data.get("service") == SERVICE_NAME
    except Exception:
        return False


def start_server_once(port: int = PORT) -> bool:
    global _SERVER_STARTED
    if _SERVER_STARTED:
        return True
    if _server_healthy(port):
        _SERVER_STARTED = True
        return True
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    except OSError:
        return False
    thread = threading.Thread(target=server.serve_forever, name="abrxs-cutter-process-control", daemon=True)
    thread.start()
    _SERVER_STARTED = True
    return True


def _print_processes(payload: dict) -> None:
    print(f"Estado: {payload.get('state')} · active={payload.get('active')}")
    for row in payload.get("processes", []):
        print(f"PID {row['pid']} · {row['kind']} · {row['elapsed']} · {row['command']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ABRXS Cutter 3.1.1 · Process Control")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("cancel")
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    sub.add_parser("serve")
    p = sub.add_parser("panels")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("stop-panel")
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "probe":
        payload = status_payload()
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            _print_processes(payload)
        return 0 if payload.get("ok") else 2
    if args.cmd == "cancel":
        result = cancel_all()
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "panels":
        rows = process_table()
        panels = find_control_panels(rows)
        payload = {"ok": True, "pids": [p.pid for p in panels], "processes": [{"pid": p.pid, "elapsed": p.elapsed, "command": p.command} for p in panels]}
        print(json.dumps(payload, ensure_ascii=False) if args.json else json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "stop-panel":
        result = stop_control_panels()
        print(json.dumps(result, ensure_ascii=False) if args.json else json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "serve":
        server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
        print(f"{SERVICE_NAME} http://127.0.0.1:{PORT}")
        server.serve_forever()
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

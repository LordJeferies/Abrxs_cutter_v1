#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "apps" / "cutter" / "current"
PROCESS_MODULE = CURRENT / "ABRXOS_CUTTER_PROCESS_CONTROL_V311.py"
CONTROL_PANEL = CURRENT / "ABRXOS_CUTTER_CONTROL_PANEL_V3.py"
ENGINE = CURRENT / "ABRXOS_MULTI_HTML_CUTTER_V2.py"
VERSION_FILE = CURRENT / "VERSION.json"
MANUAL = ROOT / "tools" / "ABRXS_CUTTER_PROCESS_CONTROL.command"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("abrxs_process_control_v311_repo_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No pude cargar {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


PS_SAMPLE = """\
 100   1 100  00:10 /usr/bin/python3 /Users/lordjef/ABRXOS_CUTTER_APP/ABRXOS_CUTTER_CONTROL_PANEL_V3.py
 200 100 200  00:05 /Users/lordjef/.abrxos/cutter/venv/bin/python3 /Users/lordjef/ABRXOS_CUTTER_APP/ABRXOS_MULTI_HTML_CUTTER_V2.py run --config /tmp/job.json
 201 200 200  00:04 /opt/homebrew/bin/ffmpeg -i master.mov -ss 1 -t 2 out.mp4
 300 100 300  00:01 awk -v needle=/Users/lordjef/ABRXOS_CUTTER_APP/ABRXOS_MULTI_HTML_CUTTER_V2.py index($0,needle){print $1}
 301 100 301  00:01 /usr/bin/python3 -c import sys; needle='ABRXOS_MULTI_HTML_CUTTER_V2.py'; print(needle)
"""


class Cutter311ProcessControlRepoContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path in [PROCESS_MODULE, CONTROL_PANEL, ENGINE, VERSION_FILE, MANUAL]:
            if not path.exists():
                raise AssertionError(f"Falta archivo de runtime/repo: {path}")
        cls.mod = load_module(PROCESS_MODULE)
        cls.control_text = CONTROL_PANEL.read_text(encoding="utf-8")
        cls.engine_text = ENGINE.read_text(encoding="utf-8")
        cls.version = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
        cls.manual_text = MANUAL.read_text(encoding="utf-8")

    def test_detector_ignores_self_referential_probe_processes(self):
        rows = self.mod.parse_process_table(PS_SAMPLE)
        render_pids = [p.pid for p in self.mod.find_render_processes(rows)]
        self.assertEqual(render_pids, [200])

    def test_descendant_tree_contains_ffmpeg(self):
        rows = self.mod.parse_process_table(PS_SAMPLE)
        self.assertEqual(self.mod.descendant_pids(rows, {200}), {200, 201})

    def test_control_panel_contains_process_widget_and_close_prompt(self):
        self.assertIn("ABRXS_PROCESS_CONTROL_V311_HOOK", self.control_text)
        self.assertIn("ABRXS Cutter · Procesos", self.control_text)
        self.assertIn("Cancelar render", self.control_text)
        self.assertIn("Dejar render en segundo plano y salir", self.control_text)

    def test_engine_registers_real_render_pid(self):
        self.assertIn("ABRXS_PROCESS_CONTROL_ENGINE_V311_HOOK", self.engine_text)
        self.assertIn("register_current_render", self.engine_text)

    def test_runtime_metadata_is_311_with_capcut_and_process_features(self):
        self.assertEqual(self.version["version"], "3.1.1")
        self.assertEqual(self.version["engineVersion"], "2.1.0")
        for feature in [
            "capcutExport",
            "outputModes",
            "sectionsManifest",
            "processControl",
            "safeCancel",
            "closePrompt",
        ]:
            self.assertIn(feature, self.version.get("features", []))

    def test_repo_manual_controller_exposes_view_and_cancel(self):
        self.assertIn("Ver procesos", self.manual_text)
        self.assertIn("Cancelar renders", self.manual_text)
        self.assertIn("probe --json", self.manual_text)
        self.assertIn("cancel --all", self.manual_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE.parent / "apps" / "cutter" / "current" / "ABRXOS_CAPCUT_EXPORT_V310.py"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("abrxos_capcut_v310_repo_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No pude cargar {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class Cutter311RepoContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module(MODULE_PATH)

    def test_three_output_modes_and_default(self):
        self.assertEqual(self.mod.CAPCUT_LAYER_VERSION, "3.1.0")
        self.assertEqual(self.mod.DEFAULT_NEW_SETUP_MODE, "complete_and_sections")
        self.assertEqual(
            self.mod.OUTPUT_MODES,
            {"complete_only", "complete_and_sections", "sections_only"},
        )

    def test_mode_flags_are_mutually_clear(self):
        self.assertTrue(self.mod.wants_complete("complete_only"))
        self.assertFalse(self.mod.wants_sections("complete_only"))
        self.assertTrue(self.mod.wants_complete("complete_and_sections"))
        self.assertTrue(self.mod.wants_sections("complete_and_sections"))
        self.assertFalse(self.mod.wants_complete("sections_only"))
        self.assertTrue(self.mod.wants_sections("sections_only"))

    def test_visible_section_filename_is_human_ordered(self):
        seg = {"role": "Hook inicial", "text": "texto de prueba"}
        name = self.mod.section_filename(1, seg)
        self.assertTrue(name.startswith("01__"), name)
        self.assertTrue(name.endswith(".mp4"), name)

    def test_runtime_version_contract_if_present(self):
        version_file = MODULE_PATH.parent / "VERSION.json"
        self.assertTrue(version_file.exists(), version_file)
        payload = json.loads(version_file.read_text(encoding="utf-8"))
        # CapCut layer remains 3.1.0, but the installed Cutter product is 3.1.1.
        self.assertEqual(payload["version"], "3.1.1")
        self.assertEqual(payload["engineVersion"], "2.1.0")
        self.assertEqual(payload["capcutExportDefault"], "complete_and_sections")


if __name__ == "__main__":
    unittest.main(verbosity=2)

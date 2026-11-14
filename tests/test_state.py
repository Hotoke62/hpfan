from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hpfan.state import hp_wmi_max_status


class CapabilityStateTests(unittest.TestCase):
    def test_reads_allowed_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capabilities.json"
            path.write_text('{"hp_wmi_max":"failed"}', encoding="utf-8")
            self.assertEqual(hp_wmi_max_status(path), "failed")

    def test_rejects_unknown_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capabilities.json"
            path.write_text('{"hp_wmi_max":"maybe"}', encoding="utf-8")
            self.assertEqual(hp_wmi_max_status(path), "untested")

    def test_rejects_oversized_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capabilities.json"
            path.write_text("x" * 4097, encoding="utf-8")
            self.assertEqual(hp_wmi_max_status(path), "untested")

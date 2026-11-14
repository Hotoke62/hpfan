from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hpfan.acpi_fan import FanBackendError, FanController, raw_to_rpm, require_supported_hardware


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.mode = "auto"

    def set_full(self) -> str:
        self.calls.append("full")
        self.mode = "full"
        return "[0x0]"

    def set_auto(self) -> str:
        self.calls.append("auto")
        self.mode = "auto"
        return "[0x0]"

    def snapshot(self) -> tuple[int, int, int]:
        if self.mode == "full":
            return 45, 45, 5461
        return 58, 58, 4237


class FanControllerTests(unittest.TestCase):
    def test_hardware_gate_accepts_only_verified_dmi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sys_vendor").write_text("HP\n", encoding="utf-8")
            (root / "product_name").write_text("HP EliteBook 840 G4\n", encoding="utf-8")
            (root / "board_name").write_text("828C\n", encoding="utf-8")

            identity = require_supported_hardware(root)
            self.assertEqual(identity["board_name"], "828C")

            (root / "board_name").write_text("different\n", encoding="utf-8")
            with self.assertRaises(FanBackendError):
                require_supported_hardware(root)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp_dir.name) / "state.json"
        self.temperature = 60.0
        self.backend = FakeBackend()
        self.controller = FanController(
            self.backend,  # type: ignore[arg-type]
            lambda: self.temperature,
            state_path=self.state_path,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_full_mode_persists_and_restores(self) -> None:
        self.controller.start()
        status = self.controller.set_mode("full")

        self.assertEqual(status.requested_mode, "full")
        self.assertEqual(status.effective_mode, "full")
        self.assertEqual(self.backend.calls, ["auto", "auto", "full"])

        restarted = FanController(
            self.backend,  # type: ignore[arg-type]
            lambda: self.temperature,
            state_path=self.state_path,
        )
        restarted.start()
        self.assertEqual(restarted.requested_mode, "full")
        self.assertEqual(self.backend.calls[-2:], ["auto", "full"])

    def test_safety_floor_forces_full_then_releases(self) -> None:
        self.controller.start()
        self.temperature = 86.0
        hot = self.controller.tick()
        self.temperature = 79.0
        cool = self.controller.tick()

        self.assertTrue(hot.safety_forced)
        self.assertEqual(hot.effective_mode, "full")
        self.assertFalse(cool.safety_forced)
        self.assertEqual(cool.effective_mode, "auto")
        self.assertEqual(self.backend.calls[-2:], ["full", "auto"])

    def test_raw_fan_conversion_matches_bios_formula(self) -> None:
        self.assertEqual(raw_to_rpm(58), 4237)
        self.assertEqual(raw_to_rpm(45), 5461)
        self.assertIsNone(raw_to_rpm(0))


if __name__ == "__main__":
    unittest.main()

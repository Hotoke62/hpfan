from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hpfan.profiles import PowerProfileController


class FakePowerProfiles:
    def __init__(self, profile: str = "balanced") -> None:
        self.profile = profile
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> tuple[int, str, str]:
        self.commands.append(command)
        if command == ["powerprofilesctl", "get"]:
            return 0, self.profile + "\n", ""
        if command[:2] == ["powerprofilesctl", "set"]:
            self.profile = command[2]
            return 0, "", ""
        return 1, "", "unexpected command"


class PowerProfileControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.state_path = root / "profile.json"
        self.no_turbo_path = root / "no_turbo"
        self.no_turbo_path.write_text("0\n", encoding="utf-8")
        self.runner = FakePowerProfiles()
        self.controller = PowerProfileController(
            state_path=self.state_path,
            no_turbo_path=self.no_turbo_path,
            runner=self.runner,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sets_quiet_profile(self) -> None:
        status = self.controller.set("quiet")
        self.assertEqual(status.logical, "quiet")
        self.assertEqual(status.power_profile, "power-saver")
        self.assertTrue(status.turbo_boost_allowed)

    def test_turbo_toggle_restores_previous_profile(self) -> None:
        self.controller.set("quiet")
        enabled = self.controller.toggle_turbo()
        restored = self.controller.toggle_turbo()

        self.assertEqual(enabled.logical, "turbo")
        self.assertEqual(enabled.previous_profile, "quiet")
        self.assertEqual(restored.logical, "quiet")
        self.assertEqual(restored.power_profile, "power-saver")

    def test_cycle_moves_to_next_profile(self) -> None:
        self.controller.set("balanced")
        status = self.controller.cycle()
        self.assertEqual(status.logical, "performance")


if __name__ == "__main__":
    unittest.main()

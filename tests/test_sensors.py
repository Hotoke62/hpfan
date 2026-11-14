from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hpfan.sensors import SysfsReader


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


class SysfsReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.hwmon = self.root / "hwmon"
        self.thermal = self.root / "thermal"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def reader(self) -> SysfsReader:
        return SysfsReader(self.hwmon, self.thermal)

    def test_reads_coretemp_and_unverified_hp_wmi_capability(self) -> None:
        coretemp = self.hwmon / "hwmon7"
        write(coretemp / "name", "coretemp\n")
        write(coretemp / "temp1_label", "Package id 0\n")
        write(coretemp / "temp1_input", "61000\n")
        write(coretemp / "temp2_label", "Core 0\n")
        write(coretemp / "temp2_input", "63000\n")
        write(coretemp / "temp3_label", "Core 1\n")
        write(coretemp / "temp3_input", "60000\n")

        hp = self.hwmon / "hwmon5"
        write(hp / "name", "hp\n")
        write(hp / "pwm1_enable", "2\n")

        snapshot = self.reader().snapshot()

        self.assertEqual(snapshot.cpu_package_c, 61.0)
        self.assertEqual(snapshot.cpu_max_c, 63.0)
        self.assertIsNone(snapshot.gpu_c)
        self.assertEqual(snapshot.fans, ())
        self.assertEqual(snapshot.controls[0].reported_mode, "automatic")
        self.assertFalse(snapshot.controls[0].manual_duty_available)
        self.assertTrue(snapshot.controls[0].max_auto_candidate)
        self.assertFalse(snapshot.controls[0].write_verified)

    def test_reads_gpu_fan_and_manual_pwm(self) -> None:
        gpu = self.hwmon / "hwmon2"
        write(gpu / "name", "amdgpu\n")
        write(gpu / "temp1_label", "edge\n")
        write(gpu / "temp1_input", "54500\n")
        write(gpu / "fan1_label", "GPU fan\n")
        write(gpu / "fan1_input", "2500\n")
        write(gpu / "pwm1_enable", "1\n")
        write(gpu / "pwm1", "128\n")

        snapshot = self.reader().snapshot()

        self.assertEqual(snapshot.gpu_c, 54.5)
        self.assertEqual(snapshot.fans[0].rpm, 2500)
        self.assertEqual(snapshot.controls[0].reported_mode, "manual")
        self.assertTrue(snapshot.controls[0].manual_duty_available)

    def test_ignores_zero_degree_acpi_gpu_reading(self) -> None:
        zone = self.thermal / "thermal_zone1"
        write(zone / "type", "GFXZ\n")
        write(zone / "temp", "0\n")

        snapshot = self.reader().snapshot()

        self.assertIsNone(snapshot.gpu_c)


if __name__ == "__main__":
    unittest.main()

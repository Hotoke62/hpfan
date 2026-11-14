"""Read temperatures, fan RPM, and fan-control capabilities from sysfs.

This module is deliberately read-only.  It discovers hwmon devices by their
reported names, because hwmon numbers can change between boots.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


_TEMP_INPUT_RE = re.compile(r"temp(\d+)_input$")
_FAN_INPUT_RE = re.compile(r"fan(\d+)_input$")
_PWM_ENABLE_RE = re.compile(r"pwm(\d+)_enable$")


@dataclass(frozen=True)
class TemperatureReading:
    domain: str
    label: str
    celsius: float
    source: str


@dataclass(frozen=True)
class FanReading:
    label: str
    rpm: int
    source: str


@dataclass(frozen=True)
class FanControl:
    hwmon_name: str
    channel: int
    enable_path: str
    duty_path: str | None
    reported_mode: str
    manual_duty_available: bool
    max_auto_candidate: bool
    write_verified: bool = False


@dataclass(frozen=True)
class SensorSnapshot:
    timestamp: str
    cpu_package_c: float | None
    cpu_max_c: float | None
    gpu_c: float | None
    temperatures: tuple[TemperatureReading, ...]
    fans: tuple[FanReading, ...]
    controls: tuple[FanControl, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SysfsReader:
    """Read a snapshot from Linux hwmon and thermal-zone sysfs."""

    def __init__(
        self,
        hwmon_root: Path | str = "/sys/class/hwmon",
        thermal_root: Path | str = "/sys/class/thermal",
    ) -> None:
        self.hwmon_root = Path(hwmon_root)
        self.thermal_root = Path(thermal_root)

    def snapshot(self) -> SensorSnapshot:
        temperatures = list(self._read_hwmon_temperatures())
        temperatures.extend(self._read_thermal_fallbacks(temperatures))
        fans = tuple(self._read_fans())
        controls = tuple(self._read_controls())

        cpu_readings = [reading for reading in temperatures if reading.domain == "cpu"]
        package_readings = [
            reading
            for reading in cpu_readings
            if "package" in reading.label.casefold()
            or "tdie" in reading.label.casefold()
        ]
        gpu_readings = [reading for reading in temperatures if reading.domain == "gpu"]

        cpu_package = (
            max(reading.celsius for reading in package_readings)
            if package_readings
            else (max((reading.celsius for reading in cpu_readings), default=None))
        )
        cpu_max = max((reading.celsius for reading in cpu_readings), default=None)
        gpu = max((reading.celsius for reading in gpu_readings), default=None)

        warnings: list[str] = []
        if cpu_max is None:
            warnings.append("No usable CPU temperature sensor was found.")
        if gpu is None:
            warnings.append("No separate usable GPU temperature sensor is exposed.")
        if not fans:
            warnings.append("Fan RPM is not exposed by the current kernel/firmware interface.")
        if not controls:
            warnings.append("No fan-control interface is exposed.")
        elif not any(control.manual_duty_available for control in controls):
            warnings.append("Manual PWM duty is not exposed; custom fan curves are unavailable.")
        if any(control.max_auto_candidate and not control.write_verified for control in controls):
            warnings.append("The hp-wmi maximum/automatic control has not been write-verified.")

        return SensorSnapshot(
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            cpu_package_c=cpu_package,
            cpu_max_c=cpu_max,
            gpu_c=gpu,
            temperatures=tuple(temperatures),
            fans=fans,
            controls=controls,
            warnings=tuple(warnings),
        )

    def _hwmon_devices(self) -> Iterable[tuple[Path, str]]:
        if not self.hwmon_root.is_dir():
            return
        for device in sorted(self.hwmon_root.glob("hwmon*")):
            name = _read_text(device / "name")
            if name:
                yield device, name

    def _read_hwmon_temperatures(self) -> Iterable[TemperatureReading]:
        for device, hwmon_name in self._hwmon_devices():
            domain = _temperature_domain(hwmon_name)
            for input_path in sorted(device.glob("temp*_input")):
                match = _TEMP_INPUT_RE.fullmatch(input_path.name)
                if not match:
                    continue
                celsius = _read_millidegrees(input_path)
                if celsius is None:
                    continue
                channel = match.group(1)
                label = _read_text(device / f"temp{channel}_label") or f"temp{channel}"
                yield TemperatureReading(
                    domain=domain,
                    label=label,
                    celsius=celsius,
                    source=str(input_path.resolve()),
                )

    def _read_thermal_fallbacks(
        self,
        existing: list[TemperatureReading],
    ) -> Iterable[TemperatureReading]:
        have_cpu = any(reading.domain == "cpu" for reading in existing)
        have_gpu = any(reading.domain == "gpu" for reading in existing)
        if not self.thermal_root.is_dir():
            return

        for zone in sorted(self.thermal_root.glob("thermal_zone*")):
            zone_type = _read_text(zone / "type")
            celsius = _read_millidegrees(zone / "temp")
            if not zone_type or celsius is None:
                continue

            folded_type = zone_type.casefold()
            if not have_cpu and folded_type in {
                "x86_pkg_temp",
                "cpu-thermal",
                "cpu_thermal",
                "soc_thermal",
            }:
                have_cpu = True
                yield TemperatureReading("cpu", zone_type, celsius, str((zone / "temp").resolve()))
            elif not have_gpu and folded_type in {"gfxz", "gpu-thermal", "gpu_thermal"}:
                have_gpu = True
                yield TemperatureReading("gpu", zone_type, celsius, str((zone / "temp").resolve()))

    def _read_fans(self) -> Iterable[FanReading]:
        for device, hwmon_name in self._hwmon_devices():
            for input_path in sorted(device.glob("fan*_input")):
                match = _FAN_INPUT_RE.fullmatch(input_path.name)
                if not match:
                    continue
                rpm = _read_int(input_path)
                if rpm is None or rpm < 0:
                    continue
                channel = match.group(1)
                label = _read_text(device / f"fan{channel}_label") or f"{hwmon_name} fan {channel}"
                yield FanReading(label=label, rpm=rpm, source=str(input_path.resolve()))

    def _read_controls(self) -> Iterable[FanControl]:
        for device, hwmon_name in self._hwmon_devices():
            for enable_path in sorted(device.glob("pwm*_enable")):
                match = _PWM_ENABLE_RE.fullmatch(enable_path.name)
                if not match:
                    continue
                channel = int(match.group(1))
                raw_mode = _read_int(enable_path)
                duty_path = device / f"pwm{channel}"
                is_hp_wmi = hwmon_name == "hp"
                yield FanControl(
                    hwmon_name=hwmon_name,
                    channel=channel,
                    enable_path=str(enable_path.resolve()),
                    duty_path=str(duty_path.resolve()) if duty_path.exists() else None,
                    reported_mode=_fan_mode(raw_mode, is_hp_wmi),
                    manual_duty_available=duty_path.exists(),
                    max_auto_candidate=is_hp_wmi,
                )


def _read_text(path: Path, limit: int = 256) -> str | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            value = handle.read(limit + 1)
    except (OSError, UnicodeError):
        return None
    if len(value) > limit:
        return None
    value = value.strip()
    return value or None


def _read_int(path: Path) -> int | None:
    value = _read_text(path, limit=32)
    if value is None:
        return None
    try:
        return int(value, 10)
    except ValueError:
        return None


def _read_millidegrees(path: Path) -> float | None:
    value = _read_int(path)
    if value is None:
        return None
    celsius = value / 1000.0
    if not 0.0 < celsius <= 150.0:
        return None
    return round(celsius, 1)


def _temperature_domain(hwmon_name: str) -> str:
    folded = hwmon_name.casefold()
    if folded in {"coretemp", "k10temp", "zenpower", "cpu_thermal", "x86_pkg_temp"}:
        return "cpu"
    if folded in {"amdgpu", "nouveau", "nvidia", "gpu_thermal"}:
        return "gpu"
    return "system"


def _fan_mode(value: int | None, hp_wmi: bool) -> str:
    if value is None:
        return "unknown"
    if hp_wmi:
        return {0: "maximum", 1: "manual", 2: "automatic"}.get(value, f"unknown ({value})")
    return {0: "disabled", 1: "manual", 2: "automatic"}.get(value, f"unknown ({value})")


def _format_temperature(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.1f}°C"


def format_text(snapshot: SensorSnapshot) -> str:
    lines = [
        f"CPU package: {_format_temperature(snapshot.cpu_package_c)}",
        f"CPU hottest: {_format_temperature(snapshot.cpu_max_c)}",
        f"GPU: {_format_temperature(snapshot.gpu_c)}",
    ]
    if snapshot.fans:
        lines.extend(f"{fan.label}: {fan.rpm} RPM" for fan in snapshot.fans)
    else:
        lines.append("Fan RPM: unavailable")

    if snapshot.controls:
        for control in snapshot.controls:
            manual = "yes" if control.manual_duty_available else "no"
            lines.append(
                f"Control: {control.hwmon_name} channel {control.channel}, "
                f"reported mode {control.reported_mode}, manual PWM {manual}"
            )
    else:
        lines.append("Control: unavailable")

    lines.extend(f"Warning: {warning}" for warning in snapshot.warnings)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read fan and temperature status without writing hardware.")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--watch",
        type=float,
        metavar="SECONDS",
        help="repeat at this interval; minimum 0.25 seconds",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.watch is not None and args.watch < 0.25:
        print("hpfan-read: --watch must be at least 0.25 seconds", file=sys.stderr)
        return 2

    reader = SysfsReader()
    try:
        while True:
            snapshot = reader.snapshot()
            if args.json:
                print(json.dumps(snapshot.to_dict(), separators=(",", ":"), sort_keys=True))
            else:
                print(format_text(snapshot))
            sys.stdout.flush()
            if args.watch is None:
                return 0
            time.sleep(args.watch)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

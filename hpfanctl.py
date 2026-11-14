#!/usr/bin/env python3
"""User-level client for safe CPU profiles and hpfan status."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PLUGIN_ROOT / "src"))

from hpfan.profiles import LOGICAL_PROFILES, PowerProfileController, ProfileError  # noqa: E402
from hpfan.acpi_fan import FanBackendError, FanServiceClient, VALID_MODES  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control CPU-only hpfan profiles safely.")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--notify", action="store_true", help="show a desktop notification")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("status", help="show the current logical and OS power profile")
    set_parser = commands.add_parser("set", help="select a logical profile")
    set_parser.add_argument("profile", choices=LOGICAL_PROFILES)
    commands.add_parser("cycle", help="cycle Auto, Quiet, Balanced, Performance, and Turbo")
    commands.add_parser("toggle-turbo", help="toggle CPU Turbo and restore the previous profile")
    fan_parser = commands.add_parser("fan", help="control the verified privileged fan backend")
    fan_commands = fan_parser.add_subparsers(dest="fan_command", required=True)
    fan_commands.add_parser("status", help="show fan-service status")
    fan_set = fan_commands.add_parser("set", help="select Auto, Full Speed, or Custom Curve")
    fan_set.add_argument("mode", choices=VALID_MODES)
    curve_parser = fan_commands.add_parser("curve", help="show or set the custom fan curve")
    curve_commands = curve_parser.add_subparsers(dest="curve_command", required=True)
    curve_commands.add_parser("show", help="show the saved custom curve")
    curve_set = curve_commands.add_parser("set", help="save and activate a custom curve")
    curve_set.add_argument("spec", help="comma-separated temperature:percent points")
    return parser


def _parse_curve_spec(spec: str) -> list[list[float | int]]:
    points: list[list[float | int]] = []
    if len(spec) > 256:
        raise FanBackendError("custom curve is too long")
    for raw_point in spec.split(","):
        fields = raw_point.strip().split(":")
        if len(fields) != 2:
            raise FanBackendError("use temperature:percent points separated by commas")
        try:
            temperature = float(fields[0])
            percent = int(fields[1])
        except ValueError as error:
            raise FanBackendError("curve points must contain numbers") from error
        points.append([temperature, percent])
    return points


def _notify(status: dict[str, object]) -> None:
    logical = str(status["logical"]).title()
    boost = status.get("turbo_boost_allowed")
    boost_text = "allowed" if boost is True else "disabled" if boost is False else "unknown"
    message = f"CPU profile: {logical}\nTurbo Boost: {boost_text}\nFan mode: unchanged"
    try:
        subprocess.run(
            ["notify-send", "HP Fan", message],
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _format_text(status: dict[str, object]) -> str:
    boost = status.get("turbo_boost_allowed")
    boost_text = "allowed" if boost is True else "disabled" if boost is False else "unknown"
    return "\n".join(
        (
            f"Profile: {str(status['logical']).title()} (CPU only)",
            f"Power profile: {status['power_profile']}",
            f"Turbo Boost: {boost_text}",
            "Fan policy: unchanged",
        )
    )


def _format_fan_text(status: dict[str, object]) -> str:
    rpm = status.get("rpm")
    rpm_text = f"{rpm} RPM" if isinstance(rpm, int) else "unavailable"
    safety = "yes" if status.get("safety_forced") is True else "no"
    return "\n".join(
        (
            f"Fan mode: {status.get('effective_mode', 'unknown')}",
            f"Requested: {status.get('requested_mode', 'unknown')}",
            f"Fan speed: {rpm_text}",
            f"Target: {status.get('target_percent', 'firmware')}%"
            if isinstance(status.get("target_percent"), int)
            else "Target: firmware controlled",
            f"Safety override: {safety}",
        )
    )


def _notify_fan(status: dict[str, object]) -> None:
    rpm = status.get("rpm")
    rpm_text = f"{rpm} RPM" if isinstance(rpm, int) else "RPM unavailable"
    mode = str(status.get("effective_mode", "unknown")).title()
    message = f"Fan mode: {mode}\n{rpm_text}"
    if status.get("safety_forced") is True:
        message += "\n85°C safety override active"
    try:
        subprocess.run(["notify-send", "HP Fan", message], check=False, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _notify_error(message: str) -> None:
    try:
        subprocess.run(
            ["notify-send", "HP Fan", str(message)[:256]], check=False, timeout=3
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    controller = PowerProfileController()
    command = args.command or "status"
    if command == "fan":
        try:
            client = FanServiceClient()
            if args.fan_command == "status":
                value = client.status()
            elif args.fan_command == "set":
                value = client.set_mode(args.mode)
            elif args.curve_command == "show":
                value = client.status()
            else:
                value = client.set_curve(_parse_curve_spec(args.spec), activate=True)
        except FanBackendError as error:
            if args.notify:
                _notify_error(str(error))
            if args.json:
                print(json.dumps({"error": str(error)}, separators=(",", ":")))
            else:
                print(f"hpfanctl: {error}", file=sys.stderr)
            return 1
        if args.notify:
            _notify_fan(value)
        if args.json:
            print(json.dumps(value, separators=(",", ":"), sort_keys=True))
        else:
            print(_format_fan_text(value))
        return 0
    try:
        if command == "status":
            status = controller.status()
        elif command == "set":
            status = controller.set(args.profile)
        elif command == "cycle":
            status = controller.cycle()
        elif command == "toggle-turbo":
            status = controller.toggle_turbo()
        else:
            raise ProfileError(f"unknown command: {command}")
    except ProfileError as error:
        if args.json:
            print(json.dumps({"error": str(error)}, separators=(",", ":")))
        else:
            print(f"hpfanctl: {error}", file=sys.stderr)
        return 1

    value = status.to_dict()
    if args.notify:
        _notify(value)
    if args.json:
        print(json.dumps(value, separators=(",", ":"), sort_keys=True))
    else:
        print(_format_text(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

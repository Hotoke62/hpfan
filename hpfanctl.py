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
    fan_set = fan_commands.add_parser("set", help="select firmware Auto or Full Speed")
    fan_set.add_argument("mode", choices=VALID_MODES)
    return parser


def _notify(status: dict[str, object]) -> None:
    logical = str(status["logical"]).title()
    boost = status.get("turbo_boost_allowed")
    boost_text = "allowed" if boost is True else "disabled" if boost is False else "unknown"
    message = f"CPU profile: {logical}\nTurbo Boost: {boost_text}\nFan: firmware Auto"
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
            "Fan policy: firmware Auto",
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    controller = PowerProfileController()
    command = args.command or "status"
    if command == "fan":
        try:
            client = FanServiceClient()
            if args.fan_command == "status":
                value = client.status()
            else:
                value = client.set_mode(args.mode)
        except FanBackendError as error:
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

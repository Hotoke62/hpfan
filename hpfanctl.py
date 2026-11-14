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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    controller = PowerProfileController()
    command = args.command or "status"
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

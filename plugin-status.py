#!/usr/bin/env python3
"""Emit one bounded JSON sensor snapshot for the Omarchy widget."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PLUGIN_ROOT / "src"))

from hpfan.sensors import SysfsReader  # noqa: E402
from hpfan.state import hp_wmi_max_status  # noqa: E402
from hpfan.profiles import PowerProfileController, ProfileError  # noqa: E402


def main() -> int:
    snapshot = SysfsReader().snapshot().to_dict()
    verification_status = hp_wmi_max_status()
    for control in snapshot.get("controls", []):
        if control.get("hwmon_name") == "hp" and control.get("max_auto_candidate") is True:
            control["verification_status"] = verification_status
            control["write_verified"] = verification_status == "passed"
    try:
        snapshot["profile"] = PowerProfileController().status().to_dict()
    except ProfileError as error:
        snapshot["profile"] = {"logical": "unknown", "error": str(error)[:256]}
    output = json.dumps(snapshot, separators=(",", ":"), sort_keys=True)
    if len(output) > 65536:
        print('{"error":"snapshot too large"}')
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

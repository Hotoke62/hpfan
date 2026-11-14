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
from hpfan.acpi_fan import FanBackendError, FanServiceClient  # noqa: E402


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
    try:
        fan_service = FanServiceClient().status()
    except FanBackendError as error:
        fan_service = {"available": False, "error": str(error)[:256]}
    snapshot["fan_service"] = fan_service
    service_rpm = fan_service.get("rpm")
    if fan_service.get("available") is True:
        snapshot["warnings"] = [
            warning
            for warning in snapshot.get("warnings", [])
            if warning != "Fan RPM is not exposed by the current kernel/firmware interface."
        ]
    if not snapshot.get("fans") and isinstance(service_rpm, int) and 0 <= service_rpm <= 100000:
        snapshot["fans"] = [
            {
                "label": "CPU fan",
                "rpm": service_rpm,
                "source": "hpfand/acpi-gfrm",
            }
        ]
    output = json.dumps(snapshot, separators=(",", ":"), sort_keys=True)
    if len(output) > 65536:
        print('{"error":"snapshot too large"}')
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

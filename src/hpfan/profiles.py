"""Unprivileged CPU power-profile control with a logical Turbo override."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


LOGICAL_PROFILES = ("auto", "quiet", "balanced", "performance", "turbo")
CYCLE_ORDER = LOGICAL_PROFILES
POWER_PROFILE = {
    "auto": "balanced",
    "quiet": "power-saver",
    "balanced": "balanced",
    "performance": "performance",
    "turbo": "performance",
}
_DERIVED_LOGICAL = {
    "power-saver": "quiet",
    "balanced": "balanced",
    "performance": "performance",
}


class ProfileError(RuntimeError):
    """Raised when a requested power-profile operation fails."""


@dataclass(frozen=True)
class ProfileStatus:
    logical: str
    power_profile: str
    previous_profile: str | None
    turbo_boost_allowed: bool | None
    fan_policy: str = "firmware-auto"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


Runner = Callable[[list[str]], tuple[int, str, str]]


def default_profile_state_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "hpfan" / "profile.json"


def _default_runner(command: list[str]) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, "", str(error)
    return completed.returncode, completed.stdout, completed.stderr


class PowerProfileController:
    def __init__(
        self,
        state_path: Path | str | None = None,
        no_turbo_path: Path | str = "/sys/devices/system/cpu/intel_pstate/no_turbo",
        runner: Runner = _default_runner,
    ) -> None:
        self.state_path = Path(state_path) if state_path is not None else default_profile_state_path()
        self.no_turbo_path = Path(no_turbo_path)
        self.runner = runner

    def status(self) -> ProfileStatus:
        actual = self._get_power_profile()
        state = self._read_state()
        logical = state.get("logical")
        if logical not in LOGICAL_PROFILES or POWER_PROFILE[logical] != actual:
            logical = _DERIVED_LOGICAL.get(actual, "auto")
        previous = state.get("previous_profile")
        if previous not in LOGICAL_PROFILES or previous == "turbo":
            previous = None
        return ProfileStatus(
            logical=logical,
            power_profile=actual,
            previous_profile=previous,
            turbo_boost_allowed=self._turbo_boost_allowed(),
        )

    def set(self, logical: str) -> ProfileStatus:
        if logical not in LOGICAL_PROFILES:
            raise ProfileError(f"unknown profile: {logical}")
        current = self.status()
        previous = current.logical if logical == "turbo" and current.logical != "turbo" else None
        return self._apply(logical, previous)

    def cycle(self) -> ProfileStatus:
        current = self.status().logical
        index = CYCLE_ORDER.index(current) if current in CYCLE_ORDER else 0
        return self.set(CYCLE_ORDER[(index + 1) % len(CYCLE_ORDER)])

    def toggle_turbo(self) -> ProfileStatus:
        current = self.status()
        if current.logical == "turbo":
            return self._apply(current.previous_profile or "balanced", None)
        return self._apply("turbo", current.logical)

    def _apply(self, logical: str, previous: str | None) -> ProfileStatus:
        target = POWER_PROFILE[logical]
        code, _stdout, stderr = self.runner(["powerprofilesctl", "set", target])
        if code != 0:
            detail = stderr.strip()[:512] or f"exit status {code}"
            raise ProfileError(f"could not set {target}: {detail}")

        self._write_state(
            {
                "logical": logical,
                "power_profile": target,
                "previous_profile": previous,
                "changed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
        return ProfileStatus(
            logical=logical,
            power_profile=target,
            previous_profile=previous,
            turbo_boost_allowed=self._turbo_boost_allowed(),
        )

    def _get_power_profile(self) -> str:
        code, stdout, stderr = self.runner(["powerprofilesctl", "get"])
        if code != 0:
            detail = stderr.strip()[:512] or f"exit status {code}"
            raise ProfileError(f"could not read the power profile: {detail}")
        profile = stdout.strip()
        if profile not in _DERIVED_LOGICAL:
            raise ProfileError(f"unsupported power profile reported: {profile or 'empty'}")
        return profile

    def _turbo_boost_allowed(self) -> bool | None:
        try:
            value = self.no_turbo_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return None
        if value == "0":
            return True
        if value == "1":
            return False
        return None

    def _read_state(self) -> dict[str, object]:
        try:
            if self.state_path.stat().st_size > 4096:
                return {}
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_state(self, value: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".profile.",
            dir=self.state_path.parent,
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.state_path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

"""Read bounded, machine-local fan capability verification state."""

from __future__ import annotations

import json
import os
from pathlib import Path


_ALLOWED_STATUSES = {"untested", "passed", "failed"}


def default_state_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "hpfan" / "capabilities.json"


def hp_wmi_max_status(path: Path | str | None = None) -> str:
    state_path = Path(path) if path is not None else default_state_path()
    try:
        if state_path.stat().st_size > 4096:
            return "untested"
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "untested"

    status = data.get("hp_wmi_max") if isinstance(data, dict) else None
    return status if status in _ALLOWED_STATUSES else "untested"

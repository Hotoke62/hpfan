"""Verified HP EliteBook 840 G4 ACPI fan backend and safety controller."""

from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


STMM_METHOD = r"\_SB.WMIV.STMM"
GFRM_METHOD = r"\_TZ.GFRM"
FULL_SPEED_BUFFER = "b230164"
FIRMWARE_AUTO_BUFFER = "bAA"
FAN_ACTUAL_REGISTER = 0x2E
FAN_TARGET_REGISTER = 0x2F
FULL_SPEED_RAW = 45
RPM_NUMERATOR = 0x3C000
VALID_MODES = ("auto", "full")
DEFAULT_SOCKET_PATH = Path("/run/hpfan/control.sock")
SUPPORTED_DMI = {
    "sys_vendor": "HP",
    "product_name": "HP EliteBook 840 G4",
    "board_name": "828C",
}


class FanBackendError(RuntimeError):
    """Raised when the verified fan backend cannot complete an operation."""


def require_supported_hardware(dmi_root: Path | str = "/sys/class/dmi/id") -> dict[str, str]:
    """Refuse ACPI fan control unless all verified DMI identifiers match."""

    root = Path(dmi_root)
    identity: dict[str, str] = {}
    for field, expected in SUPPORTED_DMI.items():
        try:
            value = (root / field).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise FanBackendError(f"cannot verify hardware identity: {field}") from error
        identity[field] = value
        if value != expected:
            raise FanBackendError(
                "unsupported hardware: "
                f"{identity.get('sys_vendor', '?')} / "
                f"{identity.get('product_name', '?')} / "
                f"board {identity.get('board_name', '?')}"
            )
    return identity


@dataclass(frozen=True)
class FanStatus:
    available: bool
    backend: str
    requested_mode: str
    effective_mode: str
    safety_forced: bool
    safety_floor_c: float
    safety_release_c: float
    rpm: int | None
    actual_raw: int | None
    target_raw: int | None
    cpu_max_c: float | None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class AcpiCallBackend:
    """Call only the fan methods verified in this machine's own DSDT."""

    def __init__(
        self,
        call_path: Path | str = "/proc/acpi/call",
        ec_path: Path | str = "/sys/kernel/debug/ec/ec0/io",
    ) -> None:
        self.call_path = Path(call_path)
        self.ec_path = Path(ec_path)

    def set_full(self) -> str:
        return self._call(f"{STMM_METHOD} {FULL_SPEED_BUFFER}")

    def set_auto(self) -> str:
        result = self._call(f"{STMM_METHOD} {FIRMWARE_AUTO_BUFFER}")
        for _attempt in range(10):
            target = self.read_register(FAN_TARGET_REGISTER)
            if target is None or target != FULL_SPEED_RAW:
                return result
            time.sleep(0.5)
        self._call(f"{STMM_METHOD} {FIRMWARE_AUTO_BUFFER}")
        for _attempt in range(6):
            target = self.read_register(FAN_TARGET_REGISTER)
            if target is None or target != FULL_SPEED_RAW:
                return result
            time.sleep(0.5)
        raise FanBackendError("BIOS reset returned success but the full-speed target remained active")

    def bios_rpm(self) -> int | None:
        result = self._call(GFRM_METHOD)
        match = re.fullmatch(r"0x([0-9a-fA-F]+)", result)
        return int(match.group(1), 16) if match else None

    def read_register(self, offset: int) -> int | None:
        if not 0 <= offset <= 0xFF:
            return None
        try:
            with self.ec_path.open("rb", buffering=0) as handle:
                handle.seek(offset)
                value = handle.read(1)
        except OSError:
            return None
        return value[0] if len(value) == 1 else None

    def snapshot(self) -> tuple[int | None, int | None, int | None]:
        actual = self.read_register(FAN_ACTUAL_REGISTER)
        target = self.read_register(FAN_TARGET_REGISTER)
        try:
            rpm = self.bios_rpm()
        except FanBackendError:
            rpm = raw_to_rpm(actual)
        return actual, target, rpm

    def _call(self, expression: str) -> str:
        if len(expression) > 256 or "\n" in expression or "\r" in expression:
            raise FanBackendError("invalid ACPI expression")
        try:
            self.call_path.write_text(expression + "\n", encoding="ascii")
            raw = self.call_path.read_bytes()[:4096]
        except OSError as error:
            raise FanBackendError(f"ACPI call unavailable: {error}") from error
        result = raw.replace(b"\0", b"").decode("ascii", errors="replace").strip()
        if not result:
            raise FanBackendError("ACPI call returned no result")
        if result.startswith("Error:"):
            raise FanBackendError(result[:512])
        return result


def raw_to_rpm(raw: int | None) -> int | None:
    if raw is None or raw <= 0:
        return None
    return (RPM_NUMERATOR + raw // 2) // raw


class FanController:
    """Serialize control requests and enforce the independent thermal floor."""

    def __init__(
        self,
        backend: AcpiCallBackend,
        temperature_reader: Callable[[], float | None],
        state_path: Path | str = "/var/lib/hpfan/state.json",
        safety_floor_c: float = 85.0,
        safety_release_c: float = 80.0,
    ) -> None:
        if safety_release_c >= safety_floor_c:
            raise ValueError("safety release must be below the safety floor")
        self.backend = backend
        self.temperature_reader = temperature_reader
        self.state_path = Path(state_path)
        self.safety_floor_c = safety_floor_c
        self.safety_release_c = safety_release_c
        self.requested_mode = "auto"
        self.effective_mode = "auto"
        self.safety_forced = False
        self.last_error: str | None = None
        self.lock = threading.RLock()

    def start(self) -> None:
        with self.lock:
            self.backend.set_auto()
            self.requested_mode = self._read_state()
            self._apply(self.requested_mode)

    def stop(self) -> None:
        with self.lock:
            self.backend.set_auto()
            self.effective_mode = "auto"
            self.safety_forced = False

    def set_mode(self, mode: str) -> FanStatus:
        if mode not in VALID_MODES:
            raise FanBackendError(f"unsupported fan mode: {mode}")
        with self.lock:
            self.requested_mode = mode
            self._write_state(mode)
            if not self.safety_forced:
                self._apply(mode)
            return self.status()

    def tick(self) -> FanStatus:
        with self.lock:
            temperature = self.temperature_reader()
            if temperature is not None and temperature >= self.safety_floor_c:
                if not self.safety_forced or self.effective_mode != "full":
                    self.backend.set_full()
                    self.effective_mode = "full"
                self.safety_forced = True
            elif self.safety_forced and temperature is not None and temperature <= self.safety_release_c:
                self.safety_forced = False
                self._apply(self.requested_mode)
            return self._status_with_temperature(temperature)

    def status(self) -> FanStatus:
        with self.lock:
            return self._status_with_temperature(self.temperature_reader())

    def _status_with_temperature(self, temperature: float | None) -> FanStatus:
        try:
            actual, target, rpm = self.backend.snapshot()
            error = self.last_error
        except FanBackendError as backend_error:
            actual, target, rpm = None, None, None
            error = str(backend_error)[:512]
        observed_mode = self.effective_mode
        if target is not None:
            observed_mode = "full" if target <= FULL_SPEED_RAW else "auto"
        return FanStatus(
            available=True,
            backend="hp-elitebook-840-g4-acpi-stmm",
            requested_mode=self.requested_mode,
            effective_mode=observed_mode,
            safety_forced=self.safety_forced,
            safety_floor_c=self.safety_floor_c,
            safety_release_c=self.safety_release_c,
            rpm=rpm,
            actual_raw=actual,
            target_raw=target,
            cpu_max_c=temperature,
            error=error,
        )

    def _apply(self, mode: str) -> None:
        try:
            if mode == "full":
                self.backend.set_full()
            else:
                self.backend.set_auto()
            self.effective_mode = mode
            self.last_error = None
        except FanBackendError as error:
            self.last_error = str(error)[:512]
            raise

    def _read_state(self) -> str:
        try:
            if self.state_path.stat().st_size > 4096:
                return "auto"
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return "auto"
        mode = value.get("mode") if isinstance(value, dict) else None
        return mode if mode in VALID_MODES else "auto"

    def _write_state(self, mode: str) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        temporary = self.state_path.with_name(f".{self.state_path.name}.{os.getpid()}")
        temporary.write_text(json.dumps({"mode": mode}) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.state_path)


class FanServiceClient:
    def __init__(self, socket_path: Path | str = DEFAULT_SOCKET_PATH) -> None:
        self.socket_path = Path(socket_path)

    def status(self) -> dict[str, object]:
        return self.request({"command": "status"})

    def set_mode(self, mode: str) -> dict[str, object]:
        if mode not in VALID_MODES:
            raise FanBackendError(f"unsupported fan mode: {mode}")
        return self.request({"command": "set_mode", "mode": mode})

    def request(self, payload: dict[str, object]) -> dict[str, object]:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > 4096:
            raise FanBackendError("fan-service request is too large")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(12.0)
                client.connect(str(self.socket_path))
                client.sendall(encoded)
                response = bytearray()
                while len(response) <= 65536:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    response.extend(chunk)
                    if b"\n" in chunk:
                        break
        except OSError as error:
            raise FanBackendError(f"fan service unavailable: {error}") from error
        if len(response) > 65536:
            raise FanBackendError("fan-service response is too large")
        try:
            value = json.loads(bytes(response).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise FanBackendError("invalid fan-service response") from error
        if not isinstance(value, dict):
            raise FanBackendError("invalid fan-service response")
        if value.get("ok") is not True:
            raise FanBackendError(str(value.get("error", "fan-service request failed"))[:512])
        status = value.get("status")
        if not isinstance(status, dict):
            raise FanBackendError("fan-service response has no status")
        return status

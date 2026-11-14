#!/usr/bin/env python3
"""Privileged, model-gated HP fan-control service."""

from __future__ import annotations

import grp
import json
import os
import signal
import socketserver
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from hpfan.acpi_fan import (  # noqa: E402
    AcpiCallBackend,
    FanBackendError,
    FanController,
    require_supported_hardware,
)


SOCKET_PATH = Path("/run/hpfan/control.sock")
MAX_REQUEST = 4096


def cpu_max_temperature() -> float | None:
    maximum: float | None = None
    for path in Path("/sys/devices/platform").glob("coretemp.*/hwmon/hwmon*/temp*_input"):
        try:
            raw = int(path.read_text(encoding="ascii").strip())
        except (OSError, UnicodeError, ValueError):
            continue
        value = raw / 1000.0
        if 0.0 < value <= 150.0:
            maximum = value if maximum is None else max(maximum, value)
    return maximum


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.connection.settimeout(3.0)
        raw = self.rfile.readline(MAX_REQUEST + 1)
        if not raw or len(raw) > MAX_REQUEST:
            self._send_error("invalid request size")
            return
        try:
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._send_error("invalid JSON")
            return
        if not isinstance(request, dict):
            self._send_error("request must be an object")
            return

        controller: FanController = self.server.controller  # type: ignore[attr-defined]
        command = request.get("command")
        try:
            if command == "status":
                status = controller.status()
            elif command == "set_mode":
                status = controller.set_mode(str(request.get("mode", "")))
            else:
                raise FanBackendError("unknown command")
        except FanBackendError as error:
            self._send_error(str(error)[:512])
            return
        self._send({"ok": True, "status": status.to_dict()})

    def _send_error(self, message: str) -> None:
        self._send({"ok": False, "error": message})

    def _send(self, value: dict[str, object]) -> None:
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
        try:
            self.wfile.write(encoded[:65536])
        except (BrokenPipeError, ConnectionResetError):
            pass


class FanServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, path: str, controller: FanController) -> None:
        self.controller = controller
        super().__init__(path, RequestHandler)


def monitor(controller: FanController, stop_event: threading.Event) -> None:
    while not stop_event.wait(1.0):
        try:
            controller.tick()
        except FanBackendError:
            pass


def main() -> int:
    if os.geteuid() != 0:
        print("hpfand: must run as root", file=sys.stderr)
        return 1

    try:
        require_supported_hardware()
    except FanBackendError as error:
        print(f"hpfand: {error}", file=sys.stderr)
        return 1

    wheel_gid = grp.getgrnam("wheel").gr_gid
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    os.chown(SOCKET_PATH.parent, 0, wheel_gid)
    os.chmod(SOCKET_PATH.parent, 0o750)
    SOCKET_PATH.unlink(missing_ok=True)
    controller = FanController(AcpiCallBackend(), cpu_max_temperature)
    controller.start()
    server = FanServer(str(SOCKET_PATH), controller)
    os.chown(SOCKET_PATH, 0, wheel_gid)
    os.chmod(SOCKET_PATH, 0o660)

    stop_event = threading.Event()
    monitor_thread = threading.Thread(target=monitor, args=(controller, stop_event), daemon=True)
    monitor_thread.start()

    def stop(_signum: int, _frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    exit_code = 0
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        stop_event.set()
        server.server_close()
        SOCKET_PATH.unlink(missing_ok=True)
        try:
            controller.stop()
        except FanBackendError as error:
            print(f"hpfand: firmware reset failed: {error}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

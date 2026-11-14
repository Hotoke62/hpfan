#!/usr/bin/env bash

set -Eeuo pipefail

if [[ $EUID -ne 0 ]]; then
  printf 'ERROR: run this remover as root.\n' >&2
  exit 1
fi

kernel_release="$(uname -r)"

systemctl disable --now hpfand.service >/dev/null 2>&1 || true
if [[ -w /proc/acpi/call ]]; then
  printf '%s\n' '\_SB.WMIV.STMM bAA' > /proc/acpi/call
  cat /proc/acpi/call >/dev/null 2>&1 || true
fi
rm -f /etc/systemd/system/hpfand.service
rm -f "/usr/lib/modules/$kernel_release/extramodules/acpi_call.ko"
rm -rf /usr/local/lib/hpfan
depmod -a "$kernel_release"
systemctl daemon-reload

printf 'Removed hpfand and restored firmware Auto.\n'

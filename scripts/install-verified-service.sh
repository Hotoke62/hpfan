#!/usr/bin/env bash

set -Eeuo pipefail

if [[ $EUID -ne 0 ]]; then
  printf 'ERROR: run this installer as root.\n' >&2
  exit 1
fi

if [[ $# -ne 1 ]]; then
  printf 'Usage: %s /path/to/acpi_call.ko\n' "$0" >&2
  exit 2
fi

module_source="$(readlink -f "$1")"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
kernel_release="$(uname -r)"
module_dir="/usr/lib/modules/$kernel_release/extramodules"

[[ -f "$module_source" ]] || {
  printf 'ERROR: module does not exist: %s\n' "$module_source" >&2
  exit 1
}

vendor="$(</sys/class/dmi/id/sys_vendor)"
product="$(</sys/class/dmi/id/product_name)"
board="$(</sys/class/dmi/id/board_name)"
if [[ "$vendor" != "HP" || "$product" != "HP EliteBook 840 G4" || "$board" != "828C" ]]; then
  printf 'ERROR: refusing unsupported hardware: %s / %s / board %s\n' \
    "$vendor" "$product" "$board" >&2
  exit 1
fi

vermagic="$(modinfo -F vermagic "$module_source")"
if [[ "$vermagic" != "$kernel_release"* ]]; then
  printf 'ERROR: acpi_call module is for a different kernel: %s\n' "$vermagic" >&2
  exit 1
fi

install -d -m 0755 /usr/local/lib/hpfan/src/hpfan "$module_dir"
install -d -m 0750 /var/lib/hpfan
install -m 0755 "$project_root/hpfand.py" /usr/local/lib/hpfan/hpfand.py
install -m 0644 "$project_root/src/hpfan/"*.py /usr/local/lib/hpfan/src/hpfan/
install -m 0755 "$project_root/systemd/hpfan-reset" /usr/local/lib/hpfan/hpfan-reset
install -m 0644 "$project_root/systemd/hpfand.service" /etc/systemd/system/hpfand.service
install -m 0644 "$module_source" "$module_dir/acpi_call.ko"

depmod -a "$kernel_release"
systemctl disable --now nbfc_service.service >/dev/null 2>&1 || true
systemctl daemon-reload
systemctl enable --now hpfand.service

printf 'Installed verified fan service for %s (%s).\n' "$product" "$kernel_release"
systemctl --no-pager --full status hpfand.service

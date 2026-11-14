#!/usr/bin/env bash

set -Eeuo pipefail

readonly STMM_METHOD='\_SB.WMIV.STMM'
readonly GFRM_METHOD='\_TZ.GFRM'
readonly GTRM_METHOD='\_TZ.GTRM'
readonly RESET_BUFFER='bAA'
readonly MAX_TEST_TEMP_MILLIC=75000

if [[ $EUID -ne 0 ]]; then
  printf 'ERROR: run this verifier as root.\n' >&2
  exit 1
fi

vendor="$(</sys/class/dmi/id/sys_vendor)"
product="$(</sys/class/dmi/id/product_name)"
board="$(</sys/class/dmi/id/board_name)"
if [[ "$vendor" != 'HP' || "$product" != 'HP EliteBook 840 G4' || "$board" != '828C' ]]; then
  printf 'ERROR: unsupported hardware: %s / %s / board %s\n' "$vendor" "$product" "$board" >&2
  exit 1
fi

if [[ ! -w /proc/acpi/call ]]; then
  printf 'ERROR: /proc/acpi/call is unavailable.\n' >&2
  exit 1
fi

acpi_call() {
  local expression="$1"
  printf '%s\n' "$expression" > /proc/acpi/call
  tr -d '\000' < /proc/acpi/call
}

cpu_max_millic() {
  local path raw maximum=0
  for path in /sys/devices/platform/coretemp.*/hwmon/hwmon*/temp*_input; do
    [[ -r "$path" ]] || continue
    raw="$(<"$path")"
    [[ "$raw" =~ ^[0-9]+$ ]] || continue
    (( raw > maximum && raw <= 150000 )) && maximum="$raw"
  done
  printf '%d' "$maximum"
}

set_percent() {
  local percent="$1" hex result
  printf -v hex '%02X' "$percent"
  result="$(acpi_call "$STMM_METHOD b2301${hex}")"
  [[ "$result" != Error:* ]] || {
    printf 'ERROR: BIOS rejected %s%%: %s\n' "$percent" "$result" >&2
    return 1
  }
}

service_was_active=false
if systemctl is-active --quiet hpfand.service; then
  service_was_active=true
  systemctl stop hpfand.service
fi

cleanup_done=false
cleanup() {
  local previous_status=$?
  if [[ "$cleanup_done" != true ]]; then
    cleanup_done=true
    acpi_call "$STMM_METHOD $RESET_BUFFER" >/dev/null 2>&1 || true
    if [[ "$service_was_active" == true ]]; then
      systemctl start hpfand.service || true
    fi
  fi
  return "$previous_status"
}
trap cleanup EXIT HUP INT TERM

temperature="$(cpu_max_millic)"
if (( temperature <= 0 || temperature >= MAX_TEST_TEMP_MILLIC )); then
  printf 'ERROR: unsafe or unavailable starting CPU temperature: %s m°C\n' "$temperature" >&2
  exit 1
fi

printf 'Verified hardware: %s / %s / board %s\n' "$vendor" "$product" "$board"
printf 'Starting CPU temperature: %d.%d°C\n' "$((temperature / 1000))" "$(((temperature % 1000) / 100))"

for percent in 40 60 80; do
  printf '\nRequesting %s%% through the BIOS STMM method...\n' "$percent"
  set_percent "$percent"
  for second in 1 2 3 4 5; do
    sleep 1
    temperature="$(cpu_max_millic)"
    if (( temperature <= 0 || temperature >= MAX_TEST_TEMP_MILLIC )); then
      printf 'ERROR: stopping at CPU temperature %s m°C.\n' "$temperature" >&2
      exit 1
    fi
    actual="$(acpi_call "$GFRM_METHOD")"
    target="$(acpi_call "$GTRM_METHOD")"
    printf '  %ss: actual %s, target %s, CPU %d.%d°C\n' \
      "$second" "$actual" "$target" "$((temperature / 1000))" "$(((temperature % 1000) / 100))"
  done
done

printf '\nRestoring Firmware Auto...\n'
acpi_call "$STMM_METHOD $RESET_BUFFER" >/dev/null
cleanup
trap - EXIT HUP INT TERM
printf 'Verification complete; hpfand is active again in its saved mode.\n'

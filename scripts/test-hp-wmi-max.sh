#!/usr/bin/env bash

set -Eeuo pipefail

find_hp_control() {
  local device

  for device in /sys/class/hwmon/hwmon*; do
    [[ -r "$device/name" ]] || continue
    [[ "$(<"$device/name")" == "hp" ]] || continue
    [[ -e "$device/pwm1_enable" ]] || continue
    readlink -f "$device/pwm1_enable"
    return 0
  done

  return 1
}

control_path="$(find_hp_control || true)"
if [[ -z "$control_path" ]]; then
  printf 'ERROR: hp-wmi pwm1_enable was not found. Nothing was changed.\n' >&2
  exit 1
fi

initial_mode="$(<"$control_path")"
printf 'Control: %s\n' "$control_path"
printf 'Initial reported mode: %s (2 means firmware automatic)\n' "$initial_mode"

if [[ "$initial_mode" != "2" ]]; then
  printf 'ERROR: refusing the test because the starting mode is not automatic.\n' >&2
  exit 1
fi

test_mode="single"
case "${1:-}" in
  --probe)
    test_mode="probe"
    ;;
  --pulse)
    test_mode="pulse"
    ;;
  "")
    ;;
  *)
    printf 'Usage: %s [--probe|--pulse]\n' "$0" >&2
    exit 2
    ;;
esac

if [[ "$test_mode" == "probe" ]]; then
  printf 'Probe complete. No write was attempted.\n'
  exit 0
fi

if [[ ! -t 0 ]]; then
  printf 'ERROR: run this test in an interactive terminal so sudo and observation are available.\n' >&2
  exit 1
fi

if [[ "$test_mode" == "pulse" ]]; then
  printf '\nThis test alternates Maximum and Auto twice for an audible A/B comparison.\n'
else
  printf '\nThis test requests maximum fan for five seconds, then restores firmware Auto.\n'
fi
printf 'It uses the kernel hp-wmi interface and does not access raw EC registers.\n\n'

cpu_max_millidegrees=0
for input in /sys/class/hwmon/hwmon*/temp*_input; do
  [[ -r "$input" ]] || continue
  value="$(<"$input")"
  [[ "$value" =~ ^[0-9]+$ ]] || continue
  (( value > cpu_max_millidegrees && value <= 150000 )) && cpu_max_millidegrees="$value"
done
if [[ "$test_mode" == "pulse" && "$cpu_max_millidegrees" -gt 70000 ]]; then
  printf 'ERROR: CPU is currently %.1f°C. Wait until it is below 70°C, then retry.\n' \
    "$((cpu_max_millidegrees / 100))e-1" >&2
  exit 1
fi

sudo -v

write_mode() {
  local mode="$1"
  printf '%s\n' "$mode" | sudo tee "$control_path" >/dev/null
}

record_verification() {
  local status="$1"
  local state_home="${XDG_STATE_HOME:-$HOME/.local/state}"
  local state_dir="$state_home/hpfan"
  local temporary

  [[ "$status" == "passed" || "$status" == "failed" ]] || return 1
  umask 077
  mkdir -p "$state_dir"
  temporary="$(mktemp "$state_dir/.capabilities.XXXXXX")"
  printf '{\n  "hp_wmi_max": "%s",\n  "observed_at": "%s"\n}\n' \
    "$status" "$(date --iso-8601=date)" > "$temporary"
  mv "$temporary" "$state_dir/capabilities.json"
}

auto_restored=false
restore_auto() {
  local previous_status=$?

  if [[ "$auto_restored" != true ]]; then
    printf '\nRestoring firmware automatic control...\n' >&2
    if write_mode 2; then
      auto_restored=true
      printf 'Restore command completed; reported mode is %s.\n' "$(<"$control_path")" >&2
    else
      printf 'CRITICAL: the Auto restore command failed. Shut the laptop down fully.\n' >&2
    fi
  fi

  return "$previous_status"
}

trap restore_auto EXIT HUP INT TERM

log_start="$(date --iso-8601=seconds)"
countdown() {
  local label="$1" seconds="$2" remaining
  for ((remaining = seconds; remaining >= 1; remaining--)); do
    printf '%s: %ss remaining\r' "$label" "$remaining"
    sleep 1
  done
  printf '\n'
}

request_maximum() {
  auto_restored=false
  printf 'Requesting maximum fan. Listen for a clear increase...\n'
  if ! write_mode 0; then
    printf 'RESULT: hp-wmi rejected maximum-fan mode.\n' >&2
    exit 1
  fi
  printf 'Kernel accepted the request; reported mode is %s.\n' "$(<"$control_path")"
}

request_auto() {
  printf 'Requesting firmware Auto. Listen for a decrease...\n'
  if ! write_mode 2; then
    printf 'CRITICAL: hp-wmi rejected the Auto restore command. Shut the laptop down fully.\n' >&2
    exit 1
  fi
  auto_restored=true
  printf 'Auto request accepted; reported mode is %s.\n' "$(<"$control_path")"
}

if [[ "$test_mode" == "pulse" ]]; then
  request_maximum
  countdown "MAXIMUM pulse 1" 15
  request_auto
  countdown "AUTO interval" 15
  request_maximum
  countdown "MAXIMUM pulse 2" 15
  request_auto
else
  request_maximum
  countdown "Maximum request" 5
  request_auto
fi

printf '\nRelevant kernel messages from this test:\n'
journalctl -b -k --since "$log_start" --no-pager 2>/dev/null |
  rg -i 'hp[-_ ]wmi|fan' || true

if [[ "$test_mode" == "pulse" ]]; then
  printf '\nDid the fan clearly follow both Maximum/Auto sound changes? [y/N] '
else
  printf '\nDid the fan audibly speed up during the five-second maximum request? [y/N] '
fi
read -r observed
case "$observed" in
  y|Y|yes|YES|Yes)
    record_verification passed
    printf 'RESULT: maximum/Auto control is physically observed as working.\n'
    ;;
  *)
    record_verification failed
    printf 'RESULT: maximum-fan operation was not physically verified.\n'
    ;;
esac

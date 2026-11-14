#!/usr/bin/env bash

set -Eeuo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
client="$project_root/hpfanctl.py"
status_helper="$project_root/plugin-status.py"
test_script="$project_root/scripts/test-hp-wmi-max.sh"

previous_profile="$(python3 "$client" --json status | jq -r '.logical')"
case "$previous_profile" in
  auto|quiet|balanced|performance|turbo) ;;
  *) previous_profile="balanced" ;;
esac

profile_restored=false
restore_profile() {
  local previous_status=$?

  if [[ "$profile_restored" != true ]]; then
    printf '\nRestoring previous CPU profile: %s\n' "$previous_profile" >&2
    python3 "$client" set "$previous_profile" >/dev/null 2>&1 || true
    profile_restored=true
  fi
  return "$previous_status"
}

trap restore_profile EXIT HUP INT TERM

printf 'Temporarily selecting Quiet so the fan test starts from a cool baseline.\n'
python3 "$client" set quiet >/dev/null

for attempt in {1..24}; do
  cpu_temp="$(python3 "$status_helper" | jq -r '.cpu_max_c // 999')"
  printf 'Cooling baseline: %s°C\r' "$cpu_temp"
  if awk -v value="$cpu_temp" 'BEGIN { exit !(value < 65) }'; then
    printf '\nCool baseline reached.\n'
    break
  fi
  sleep 5
done
printf '\n'

"$test_script" --pulse

restore_profile
trap - EXIT HUP INT TERM

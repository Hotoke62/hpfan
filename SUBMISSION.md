# Plugin publication information

## Summary

HP Fan Monitor is an Omarchy bar widget that reads Linux hwmon temperature and
fan capability data. Version 0.1.0 is monitoring-only.

## Runtime behavior

- Runs the bundled `plugin-status.py` helper every two seconds by default.
- Reads files below `/sys/class/hwmon` and `/sys/class/thermal`.
- Produces at most 64 KiB of local JSON per sample.
- Displays only validated numeric values and fixed translated strings.
- Makes no network requests.
- Does not run as root.
- Does not write sysfs, BIOS settings, or embedded-controller registers.

## Permissions and dependencies

- Python 3
- Omarchy Shell / Quickshell
- Read access to standard Linux hwmon and thermal sysfs nodes

No additional package or kernel module is installed by the plugin.

## Known limitations

On the tested HP EliteBook 840 G4, the firmware does not expose fan RPM,
separate Intel GPU temperature, or manual PWM duty. The widget explicitly
shows these values as unavailable rather than estimating them.

The repository contains a separate interactive HP WMI maximum/Auto test. That
test requires sudo and is never launched by the plugin.

On the original EliteBook 840 G4 test machine, the maximum-fan request produced
no audible speed increase. The machine is recorded locally as failed
verification and remains under firmware automatic control.

## Safety review

The plugin does not use `ec_sys` or an NBFC configuration. Similar-model EC
register maps are intentionally rejected because incorrect writes can disable
cooling, affect charging, or hang the embedded controller.

# Changelog

## 0.3.0 - 2026-11-14

- Add a native clickable Omarchy popup panel.
- Add profile buttons for Auto, Quiet, Balanced, Performance, and CPU Turbo.
- Add a separate fan-control section showing Firmware Auto as active.
- Show Full Speed and Custom Curve as disabled with the confirmed BIOS reason.
- Change left click to open the panel; middle click cycles profiles and right
  click toggles CPU Turbo.

## 0.2.0 - 2026-11-14

- Add unprivileged Auto, Quiet, Balanced, Performance, and CPU Turbo profiles.
- Add profile cycling on left click and CPU Turbo toggle on right click.
- Remember the prior logical profile when Turbo is toggled.
- Keep fan policy explicitly under firmware automatic control.
- Add a longer two-pulse HP WMI maximum/Auto verification test.
- Treat `EINVAL` as a definitive unsupported WMI fan backend and distinguish it
  from a failed restore after a successfully accepted override.

## 0.1.0 - 2026-11-14

- Add read-only hwmon temperature and fan capability discovery.
- Add an Omarchy bar widget with bounded JSON parsing.
- Add a guarded HP WMI maximum/Auto capability test.
- Document the EliteBook 840 G4 hardware limitations and EC safety policy.
- Record machine-local HP WMI verification as passed, failed, or untested.

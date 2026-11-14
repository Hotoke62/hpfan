# Changelog

## 0.5.0 - 2026-11-14

- Verify BIOS-controlled 40%, 60%, and 80% targets through the EliteBook DSDT `STMM` percentage path.
- Add a persistent, editable custom temperature-to-fan-percentage curve.
- Enforce a verified 40% minimum and retain the independent 85°C Full Speed override.
- Make Compact the default bar appearance while keeping click-to-expand controls.

## 0.4.0 - 2026-11-14

- Verify the EliteBook 840 G4 fan map from its own DSDT.
- Add a root-only ACPI STMM service with Firmware Auto and Full Speed modes.
- Add live fan RPM reporting from the BIOS and an 85°C full-speed safety floor.
- Restore firmware control through the BIOS reset method on Auto, shutdown, or service stop.
- Enable the popup's Firmware Auto and Full Speed buttons when the service is available.
- Add Compact and Detailed bar appearance settings.
- Keep Custom Curve disabled until intermediate fan targets are physically verified.

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

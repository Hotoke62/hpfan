# Plugin publication information

## Summary

HP Fan Monitor is an Omarchy bar widget for the HP EliteBook 840 G4. It reads
Linux hwmon temperatures, selects standard CPU power profiles through
`powerprofilesctl`, and can talk to an optional model-gated root service for
verified Firmware Auto and Full Speed requests.

## Runtime behavior

- Runs the bundled `plugin-status.py` helper every two seconds by default.
- Reads files below `/sys/class/hwmon` and `/sys/class/thermal`.
- Produces at most 64 KiB of local JSON per sample.
- Displays only validated numeric values and fixed translated strings.
- Makes no network requests.
- The QML plugin and user client do not run as root.
- The optional root service calls only the test machine's verified BIOS ACPI
  methods. It never writes raw embedded-controller registers.
- On an explicit click or keybinding, may request `power-saver`, `balanced`, or
  `performance` from the existing `power-profiles-daemon` service.
- Saves the selected logical profile in the user's XDG state directory.
- Shows full-speed and custom-curve controls as disabled when no verified fan
  backend exists; clicking them performs no command.
- On the verified HP EliteBook 840 G4 board 828C only, talks to a small root
  service over a `root:wheel` Unix socket with mode `0660` for BIOS ACPI
  Auto/Full requests.
- The root service enforces full speed at 85°C, restores the requested mode at
  80°C, and calls the BIOS reset method on shutdown.
- The bar supports Compact and Detailed appearances through Omarchy's widget
  settings schema.

## Permissions and dependencies

- Python 3
- Omarchy Shell / Quickshell
- `powerprofilesctl` for CPU profile switching
- Read access to standard Linux hwmon and thermal sysfs nodes

Optional verified fan control additionally needs:

- `hpfand.service`, installed separately from the plugin
- `acpi_call.ko` built for the currently running kernel
- read-only `ec_sys` telemetry for the two verified fan registers

No package or kernel module is installed automatically by the plugin.

## Known limitations

The tested laptop does not expose a separate Intel GPU temperature or manual
PWM duty. Fan RPM is obtained through the verified BIOS `GFRM` method when the
optional service is running.

The repository contains a separate interactive HP WMI maximum/Auto test. That
test requires sudo and is never launched by the plugin.

The kernel `hp-wmi` maximum-fan interface was rejected by this BIOS with
`EINVAL`, so the plugin does not use it. Full Speed instead uses the exact
`STMM` method recovered from this machine's DSDT and physically verified at
approximately 5461 RPM. Firmware Auto uses the verified BIOS reset buffer.

Custom Curve remains disabled until intermediate STMM percentages are
physically tested and shown to restore safely.

## Safety review

The service loads `ec_sys` without write support and reads only the verified
actual/target registers (`0x2E` and `0x2F`) for telemetry. It does not use an
NBFC configuration. Similar-model EC maps are intentionally rejected because
incorrect writes can disable cooling, affect charging, or hang the embedded
controller. Both installer and daemon verify HP / EliteBook 840 G4 / board
828C before control is allowed.

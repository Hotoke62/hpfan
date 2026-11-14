# HP Fan Monitor for Omarchy

A safety-first Omarchy bar plugin and Linux sensor reader developed on an HP
EliteBook 840 G4. It reports CPU temperature, fan RPM when the firmware exposes
it, and the current kernel-reported fan mode.

Version 0.4.0 adds a verified, model-gated ACPI fan service, live RPM,
Firmware Auto, Full Speed, and Compact/Detailed bar appearances.

## Current EliteBook 840 G4 support

Test machine:

- HP EliteBook 840 G4, board 828C
- Intel Core i5-7300U and Intel HD Graphics 620
- HP BIOS P78 01.48
- Arch Linux with Omarchy

Available:

- CPU package and hottest-core temperature through `coretemp`
- ACPI and other hwmon temperature discovery
- HP WMI reported automatic/maximum mode
- Omarchy bar display and JSON output
- Auto, Quiet, Balanced, Performance, and CPU-only Turbo profiles through
  `power-profiles-daemon`
- Firmware Auto and Full Speed through the G4 BIOS's `STMM` method
- Live fan RPM through the BIOS `GFRM` method
- Independent full-speed safety override at 85°C, released at 80°C

Not currently enabled:

- Separate Intel GPU temperature
- Manual PWM duty (`pwm1` is absent)
- Custom curves, until intermediate STMM percentages are physically verified

The Linux `hp_wmi` driver exposes a possible maximum/Auto switch, but this
machine logged an invalid-parameter response during driver initialization. A
final guarded test on 2026-11-14 confirmed that the BIOS rejects both WMI fan
commands with `EINVAL`. The machine's own DSDT was then inspected and its
`STMM`, `GFRM`, `FTGC`, and `FRDC` paths were tested. Full Speed reached above
5000 RPM and the BIOS reset method restored firmware control.

## Safety policy

- Never write undocumented EC registers blindly.
- Never substitute an NBFC profile from a different laptop model.
- Restore firmware automatic control when a future controller stops.
- Keep persistent BIOS fan settings untouched so Windows remains unaffected.
- Refuse unsupported profiles instead of silently pretending they work.

The privileged service is hard-gated to HP EliteBook 840 G4 board 828C. It uses
the BIOS's ACPI methods for control, keeps `ec_sys` read-only for telemetry, and
calls the BIOS reset method on Auto and service shutdown. The installer and the
daemon independently verify all three DMI identifiers before enabling control.

## Omarchy installation

For a local development checkout:

```bash
mkdir -p ~/.config/omarchy/plugins
cp -a . ~/.config/omarchy/plugins/vee.hpfan
omarchy plugin enable vee.hpfan --before omarchy.power
```

The widget updates every two seconds by default:

- Left click opens the control panel.
- Right click toggles CPU Turbo and restores the previous profile.
- Middle click cycles Auto, Quiet, Balanced, Performance, and Turbo.

The panel contains clickable CPU profile buttons and a dedicated fan-control
section. Firmware Auto and Full Speed are active when `hpfand` is running.
Custom Curve remains visible but disabled pending physical verification.

Under the bar widget's Appearance settings, choose:

- Compact: temperature and abbreviated RPM.
- Detailed: temperature, full RPM, and CPU profile.

CPU profiles and fan mode are independent. CPU Turbo does not automatically
force Full Speed; select Full Speed separately when wanted.

The appearance selector is available from the bar editor: open the bar's
Appearance settings, select **HP Fan Monitor**, then choose **Compact** or
**Detailed** under **Bar appearance**. The setting is stored in
`~/.config/omarchy/shell.json` and survives reboot.

## Verified fan-service installation

The bar plugin itself installs no packages or kernel modules. Full Speed needs
the separate `hpfand` service and an `acpi_call.ko` built for the running
kernel. The installer refuses every machine except the verified HP EliteBook
840 G4 board 828C and refuses a module whose vermagic does not match `uname -r`:

```bash
sudo ./scripts/install-verified-service.sh /path/to/acpi_call.ko
```

After a kernel update, rebuild `acpi_call.ko` for the new kernel and rerun the
installer. To remove the service and immediately request firmware Auto:

```bash
sudo ./scripts/remove-verified-service.sh
```

The service does not change BIOS setup, firmware, or Windows. Fan mode is a
runtime ACPI request and is reset to firmware Auto when the service stops.

## CPU profile client

```bash
python3 hpfanctl.py status
python3 hpfanctl.py set quiet
python3 hpfanctl.py set balanced
python3 hpfanctl.py set performance
python3 hpfanctl.py toggle-turbo
python3 hpfanctl.py cycle
```

On Intel P-state systems, Turbo means the performance power profile while
Intel Turbo Boost remains allowed. It does not force a fixed clock and it does
not force the fan to maximum speed.

| Logical profile | OS power profile | Fan policy |
|---|---|---|
| Auto | balanced | Firmware Auto |
| Quiet | power-saver | Firmware Auto |
| Balanced | balanced | Firmware Auto |
| Performance | performance | Firmware Auto |
| Turbo | performance, temporary logical override | Firmware Auto |

## Fan service client

```bash
python3 hpfanctl.py fan status
python3 hpfanctl.py fan set full
python3 hpfanctl.py fan set auto
```

The service stores the requested fan mode under `/var/lib/hpfan/state.json`.
At 85°C it forces Full Speed regardless of the requested mode, then returns to
that mode after temperature falls to 80°C.

The logical profile is saved under `~/.local/state/hpfan/profile.json`. The
existing power-profiles daemon persists the corresponding OS power profile.

Optional Hyprland binding:

```lua
o.bind("SUPER + SHIFT + U", "Toggle CPU Turbo profile", "python3 ~/.config/omarchy/plugins/vee.hpfan/hpfanctl.py --notify toggle-turbo")
```

## Roadmap

1. Read-only sensor plugin — complete.
2. HP WMI maximum/Auto physical test — failed on the test machine.
3. CPU power-profile client — complete.
4. Verified model-specific ACPI backend — complete.
5. Hardened privileged service — complete.
6. Firmware Auto and Full Speed — complete.
7. 85°C maximum-fan safety override and firmware-Auto failsafe — complete.
8. Physically verify intermediate percentages before enabling Custom Curve.

## Stage 1: read-only sensor probe

The reader discovers hwmon devices by name and never writes to sysfs.

Run it once:

```bash
cd /home/vee/Work/hpfan
PYTHONPATH=src python3 -m hpfan.sensors
```

Machine-readable output:

```bash
PYTHONPATH=src python3 -m hpfan.sensors --json
```

Watch once per second:

```bash
PYTHONPATH=src python3 -m hpfan.sensors --watch 1
```

Run the tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

On this laptop, CPU temperature is available through the kernel. The verified
service obtains fan RPM through the BIOS `GFRM` method; a separate Intel GPU
temperature and manual PWM duty are not exposed.

## Guarded hp-wmi maximum/Auto test

First run the read-only probe:

```bash
./scripts/test-hp-wmi-max.sh --probe
```

Then run the interactive test in a terminal:

```bash
./scripts/test-hp-wmi-max.sh
```

For a final, longer audible comparison:

```bash
./scripts/test-hp-wmi-max.sh --pulse
```

Pulse mode alternates Maximum and Auto twice. It refuses to start above 70°C,
because an already-hot firmware-controlled fan makes the comparison unreliable.

The convenience wrapper temporarily selects Quiet, waits for a cooler baseline,
runs pulse mode, and restores the previous CPU profile:

```bash
./scripts/run-hp-wmi-pulse.sh
```

The script requests maximum fan for five seconds. An exit trap attempts to
restore firmware automatic control if the test succeeds, fails, or is
interrupted. The final physical observation is stored under
`$XDG_STATE_HOME/hpfan/capabilities.json` (normally
`~/.local/state/hpfan/capabilities.json`). It never loads a module or reads or
writes raw EC registers.

## Development checks

```bash
omarchy plugin validate /home/vee/Work/hpfan
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 plugin-status.py | jq .
```

## License

MIT © 2026 Vatsal Visani

## Technical references

- [Linux `hp_wmi` fan implementation](https://github.com/torvalds/linux/blob/v7.2/drivers/platform/x86/hp/hp-wmi.c#L2397-L2558)
- [NBFC-Linux model configuration catalog](https://github.com/nbfc-linux/configs/tree/main/1.0/configs)

There is currently no upstream NBFC configuration specifically for the HP
EliteBook 840 G4. Profiles for the 840 G2, 850 G3, or other HP models must not
be treated as compatible without independent register verification.

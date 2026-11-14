# HP Fan Monitor for Omarchy

A safety-first Omarchy bar plugin and Linux sensor reader developed on an HP
EliteBook 840 G4. It reports CPU temperature, fan RPM when the firmware exposes
it, and the current kernel-reported fan mode.

Version 0.2.0 adds unprivileged CPU power profiles. It does not write embedded
controller registers and does not claim that unsupported fan controls work.

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

Not exposed by this firmware/kernel combination:

- Fan RPM (`fan1_input` is absent)
- Separate Intel GPU temperature
- Manual PWM duty (`pwm1` is absent)
- A safe custom temperature-to-fan-speed curve

The Linux `hp_wmi` driver exposes a possible maximum/Auto switch, but this
machine logged an invalid-parameter response during driver initialization. A
guarded physical test on 2026-11-14 produced no audible fan-speed increase.
Maximum-fan control is therefore treated as unsupported on this machine.

## Safety policy

- Never write undocumented EC registers blindly.
- Never substitute an NBFC profile from a different laptop model.
- Restore firmware automatic control when a future controller stops.
- Keep persistent BIOS fan settings untouched so Windows remains unaffected.
- Refuse unsupported profiles instead of silently pretending they work.

Raw `ec_sys` access can disable cooling, alter charging behavior, hang the
embedded controller, or leave state active across a warm reboot. This project
will only add an EC backend after an exact model-specific register map has been
independently verified.

## Omarchy installation

For a local development checkout:

```bash
mkdir -p ~/.config/omarchy/plugins
cp -a . ~/.config/omarchy/plugins/vee.hpfan
omarchy plugin enable vee.hpfan --before omarchy.power
```

The widget updates every two seconds by default:

- Left click cycles Auto, Quiet, Balanced, Performance, and Turbo.
- Right click toggles CPU Turbo and restores the previous profile.
- Middle click refreshes the sensor reading.

These are CPU power profiles. The fan always remains under firmware automatic
control on the tested EliteBook.

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
4. Investigate only documented or model-verified fan-control backends.
5. Add a hardened privileged service only if a safe writable fan backend exists.
6. Add fan-specific Auto, Quiet, Balanced, Performance, Custom, and Turbo modes
   only where the backend can actually implement them.
7. Add an 85°C maximum-fan safety override and firmware-Auto failsafe.
8. Add boot restoration for any future fan-specific profile.

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

On this laptop, CPU temperature is available but fan RPM, a separate Intel GPU
temperature, and manual PWM duty are not currently exposed by the kernel.

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

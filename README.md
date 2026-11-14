# HP Fan Monitor for Omarchy

A safety-first Omarchy bar plugin and Linux sensor reader developed on an HP
EliteBook 840 G4. It reports CPU temperature, fan RPM when the firmware exposes
it, and the current kernel-reported fan mode.

Version 0.1.0 is deliberately monitoring-only. It does not write embedded
controller registers and does not claim that unsupported controls work.

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

Not exposed by this firmware/kernel combination:

- Fan RPM (`fan1_input` is absent)
- Separate Intel GPU temperature
- Manual PWM duty (`pwm1` is absent)
- A safe custom temperature-to-fan-speed curve

The Linux `hp_wmi` driver exposes a possible maximum/Auto switch, but this
machine logged an invalid-parameter response during driver initialization. The
write path must therefore pass the included physical test before Turbo control
is enabled.

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

The widget updates every two seconds by default. Click it to refresh. Profile
cycling will be enabled only after a writable backend passes its safety test.

## Roadmap

1. Read-only sensor plugin — complete.
2. Verify HP WMI maximum/Auto switching on physical hardware.
3. Add the hardened root service and unprivileged `hpfanctl` client.
4. Add Auto, Quiet, Balanced, Performance, Custom, and temporary Turbo modes.
5. Add an 85°C maximum-fan safety override and firmware-Auto failsafe.
6. Add Hyprland bindings and boot restoration.

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

The script requests maximum fan for five seconds. An exit trap attempts to
restore firmware automatic control if the test succeeds, fails, or is
interrupted. It never loads a module or reads or writes raw EC registers.

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

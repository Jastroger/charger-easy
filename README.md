# Juice Booster / Juice CHARGER Easy MQTT integration

This repository contains a Raspberry Pi control service for replacing the original
Juice CHARGER Easy control path and integrating the charger with EVCC or Home
Assistant via MQTT.

Important: this project changes charging behavior. Use it only if you understand
the electrical and hardware risks. The hardware current selector remains the
upper safety limit used by the software.

## Features

- MQTT control compatible with EVCC custom chargers.
- Home Assistant MQTT Discovery with controls and status entities.
- Internal PV surplus charging based on a Home Assistant grid-power MQTT value.
- Local web dashboard for live status and simple control.
- FreeCharge mode through DIP1.
- RLC current reduction through DIP2 and four RLC inputs.
- CP state reporting (`A`, `B`, `C`, `E`, `F`).
- MCP4161 RAM writes for runtime current control and EEPROM fallback on startup.
- Testable Python package with Raspberry Pi GPIO/SPI isolated in one adapter.

## Runtime behavior

The default entry point remains compatible:

```bash
python3 mqtt_client.py
```

By default it loads:

```text
/opt/juice-charger/config.yaml
```

Alternative config paths:

```bash
python3 mqtt_client.py --config ./config.yaml
CHARGER_EASY_CONFIG=./config.yaml python3 mqtt_client.py
```

The old imports also continue to work:

```python
from juice_booster_control import JuiceBoosterControl
```

## Web dashboard

The service starts a small local web dashboard when `web.enabled` is true:

```text
http://<raspberry-pi-ip>:8080/
```

The dashboard shows live charging status, PV surplus, grid power, CP-state,
hardware limits, RLC limits and the current reason for limiting or waiting. It
also lets you switch between `off`, `pv` and `instant` and set the instant
current. All hardware limits remain active.

## DIP and LED logic

The DIP switches are active-low: `ON` means the GPIO reads `LOW`.

- DIP1 ON: FreeCharge mode.
- DIP1 OFF: EVCC mode.
- DIP2 ON: RLC reductions are active.
- DIP2 OFF: RLC inputs are ignored.
- RLC inputs use pull-downs and are active when the input reads `HIGH`.

LEDs, when enabled in `config.yaml`:

- Green: EVCC mode active.
- Blue: RLC mode active.

## Current limits

The effective current is always limited by:

1. The requested MQTT/FreeCharge current.
2. The hardware maximum current selector.
3. The strongest active RLC reduction.

MQTT current payloads may be integer or decimal values. Negative values are
clamped to `0`. Invalid current payloads are ignored. The MCP4161 output is still
mapped to the known Juice Booster current curve:

```text
0A, 6A, 8A, 10A, 13A, 16A, 20A, 25A, 32A
```

## Operating modes

Home Assistant can select one of three modes through MQTT Discovery:

- `off`: charger requests `0 A`.
- `pv`: charger calculates the target current from PV surplus.
- `instant`: charger uses the configured instant current.

The physical FreeCharge DIP switch remains a hardware override. If DIP1 is ON,
the charger uses the hardware maximum while a vehicle is connected and reports
`hardware_override_free_charge` in the state JSON.

## PV surplus charging

By default Home Assistant publishes the current grid power to:

```text
juicebooster/ha/gridPower
```

Default sign convention:

- positive value: grid import
- negative value: grid export

The conservative default regulator uses one phase, 230 V, 6 A minimum current,
1 A steps, 100 W reserve, 60 s start delay, 180 s stop delay and a 60 s sensor
timeout. If the grid-power value is missing or stale, PV mode requests `0 A`
and reports `stale_grid_power`.

## MQTT topics

With the default `base_topic: juicebooster`, the service keeps these topics:

- `juicebooster/enable/set`
- `juicebooster/maxCurrent/set`
- `juicebooster/status`
- `juicebooster/enabled`
- `juicebooster/chargeCurrent`
- `juicebooster/debug/status`

Additional Home Assistant / PV topics:

- `juicebooster/mode/set`
- `juicebooster/mode`
- `juicebooster/instantCurrent/set`
- `juicebooster/instantCurrent`
- `juicebooster/ha/gridPower`
- `juicebooster/state`
- `juicebooster/availability`

Legacy behavior is preserved: `enable/set=false` switches to `off`,
`enable/set=true` switches to `instant`, and `maxCurrent/set` updates the
instant-current value.

## Home Assistant

Enable the MQTT integration in Home Assistant and point this service to the same
broker. With `home_assistant.discovery: true`, the charger publishes MQTT
Discovery payloads for:

- mode select
- instant-current number control
- current, power, CP-state and limit-reason sensors
- vehicle-connected, charging, FreeCharge-override and stale-PV-data binary sensors

Example files:

- `home_assistant/charger_easy_package.yaml`: publishes a Home Assistant grid-power sensor to MQTT.
- `home_assistant/lovelace-card.yaml`: example dashboard card for the discovered entities.

## Configuration

Use `config.yaml` as the template. Existing sections remain valid:

- `mqtt`
- `logging`
- `rlc_percentages`
- `leds`
- `buzzer`
- `home_assistant`
- `pv`
- `web`

Credentials in the example files are placeholders. Set your broker host,
username and password locally before deploying.

## Installation

On the Raspberry Pi:

```bash
python3 -m pip install -r requirements.txt
```

For development and tests:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests
python -m pytest
```

## Manual hardware test

Interactive compatibility wrapper:

```bash
sudo python3 test/set-cc.py
```

Preferred direct command:

```bash
sudo python3 -m charger_easy.tools.set_current 10
```

Add `--eeprom` only when you intentionally want to write the non-volatile MCP4161
EEPROM fallback register.

## Legal notice

All product and brand names mentioned are the property of their respective
owners. This project is not affiliated with Juice Technology AG.

## Disclaimer

I assume no liability for software errors or resulting overloads or damage to
the used hardware, the Juice Booster, the house installation, vehicles or other
equipment. Use the software at your own risk.

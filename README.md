# PV/MQTT Software for Charger Easy

Unofficial PV surplus and MQTT control software for Charger Easy hardware.

`Unofficial` `Home Assistant` `MQTT` `PV surplus charging` `Raspberry Pi`

This repository contains an open-source Raspberry Pi based software fork and
extension for installations using Juice Booster Easy / Juice CHARGER Easy
hardware. It adds local web control, MQTT integration, Home Assistant Discovery,
and PV surplus charging while keeping the hardware safety limits in place.

This is not an official Juice Technology product. Product names are used only to
describe the compatible hardware.

## Why This Exists

Many installations using Juice Booster Easy / Juice CHARGER Easy hardware
already have solid charging hardware, but not modern Home Assistant control or
PV surplus charging. This software keeps the existing hardware concept and adds:

- a Raspberry Pi control service
- MQTT command and state topics
- Home Assistant MQTT Discovery
- a local web dashboard
- PV surplus logic based on grid import/export power

The important part: hardware current limits, RLC reductions, CP vehicle state,
and the Charger Easy control board remain active boundaries.

## Features

- PV surplus charging from a Home Assistant grid-power MQTT value
- Instant charging mode with configurable current
- Pause mode that requests `0 A`
- Home Assistant MQTT Discovery
- Local dark-theme web dashboard
- Hardware current limiting through the original current selector
- FreeCharge hardware override detection
- RLC support through DIP2 and four RLC inputs
- MQTT based integration for Home Assistant and legacy EVCC-style topics

## Screenshots

see [Screenshots](docs/images/README.md)

## Safety Note

This project interacts with EV charging hardware. Mains voltage work can be
dangerous and can damage vehicles, wiring, chargers, or people if done
incorrectly.

Use this only if you understand the hardware. The software can request current,
but it cannot make an unsafe electrical installation safe. The hardware maximum
selector, RLC inputs, Control Pilot state, and original charger control board
remain the safety boundary.

## Security and Privacy

This controller software is designed for a trusted local network.

- The web dashboard and API do not implement authentication.
- The default web host `0.0.0.0` makes the dashboard reachable from the LAN.
- MQTT command topics can change charging mode and current.
- MQTT state topics are retained and expose energy, vehicle, and charger status.
- MQTT credentials in `config.yaml` are plain text.

Do not expose the web dashboard or MQTT broker to the internet. Use a private
LAN, VPN, firewall rules, and MQTT broker ACLs. If you reverse-proxy the
dashboard, bind the app to `127.0.0.1` and add authentication at the proxy.

See [Security and Privacy](docs/security-privacy.md).

## Credits

This repository is a fork of the original
[Andreas1312/charger-easy](https://github.com/Andreas1312/charger-easy)
project by Andreas1312. This fork builds on that work and adds Home Assistant,
MQTT, PV surplus, documentation, and dashboard commissioning improvements for
our use cases.

## Quick Start

### 1. Clone and Install

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

sudo mkdir -p /opt/juice-charger
sudo chown "$USER":"$USER" /opt/juice-charger

git clone https://github.com/Jastroger/charger-easy.git /opt/juice-charger/app
cd /opt/juice-charger/app

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cp config.yaml /opt/juice-charger/config.yaml
nano /opt/juice-charger/config.yaml

sudo chown root:root /opt/juice-charger/config.yaml
sudo chmod 600 /opt/juice-charger/config.yaml
```

Python 3.10 or newer is recommended.

### 2. Configure MQTT

Edit `/opt/juice-charger/config.yaml`:

```yaml
mqtt:
  broker_host: "mqtt.local"
  broker_port: 1883
  username: null
  password: null
  base_topic: "juicebooster"
```

### 3. Start Manually

```bash
cd /opt/juice-charger/app
. .venv/bin/activate
python -m charger_easy.cli --config /opt/juice-charger/config.yaml
```

Then open:

```text
http://<raspberry-pi-ip>:8080/
```

### 4. Install as a Service

Create `/etc/systemd/system/juice-charger-easy.service`:

```ini
[Unit]
Description=PV/MQTT Software for Charger Easy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/juice-charger/app
ExecStart=/opt/juice-charger/app/.venv/bin/python -m charger_easy.cli --config /opt/juice-charger/config.yaml
Restart=always
RestartSec=5
User=root
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now juice-charger-easy
sudo journalctl -u juice-charger-easy -f
```

The example service runs as `root` because GPIO and SPI access are commonly
restricted on Raspberry Pi systems. Keep the dashboard and MQTT broker on a
trusted network. A dedicated service user is preferable if your Raspberry Pi
GPIO/SPI permissions allow it.

## Home Assistant Overview

Home Assistant talks to this controller through MQTT.

With MQTT Discovery enabled, Home Assistant creates a
`PV/MQTT Software for Charger Easy` device with controls and sensors for:

- selected mode
- instant current
- CP state
- grid power
- PV surplus
- target current
- effective current
- hardware maximum
- RLC percentage
- limit reason
- vehicle connected
- charging
- hardware FreeCharge override
- stale PV input

The charger needs grid power at the grid connection point. For RCT Power setups,
use the grid meter sensor, for example:

```text
sensor.rct_power_storage_grid_power
```

Do not use raw inverter power for PV surplus charging. Inverter power does not
include house load, battery behavior, or the actual import/export state at the
grid connection point.

See [Home Assistant setup](docs/home-assistant.md).

## MQTT Overview

Default base topic:

```text
juicebooster
```

Most important topics:

| Topic | Direction | Purpose |
| --- | --- | --- |
| `juicebooster/ha/gridPower` | input | Grid import/export power for PV mode |
| `juicebooster/mode/set` | input | Set `off`, `pv`, or `instant` |
| `juicebooster/instantCurrent/set` | input | Set instant current in amps |
| `juicebooster/state` | output | Main JSON state |
| `juicebooster/availability` | output | `online` / `offline` |

Default grid power sign convention:

```text
+1000 = importing 1000 W from the grid
-2000 = exporting 2000 W to the grid
```

This matches:

```yaml
pv:
  grid_power_export_negative: true
```

See [MQTT topics and payloads](docs/mqtt.md).

## PV Surplus Logic

PV mode uses grid import/export power, not inverter output.

With the default sign convention:

```text
pv_surplus_w = -grid_power_w + current_charging_power_w - reserve_w
```

Example:

```text
grid_power_w = -2000 W
reserve_w = 100 W
pv_surplus_w = 1900 W
```

If no vehicle is connected, charging stays at `0 A`, but the dashboard still
shows grid power and PV surplus. This is intentional and useful for
commissioning.

## Configuration Overview

Use [config.yaml](config.yaml) as the template.

Important sections:

| Section | Purpose |
| --- | --- |
| `mqtt` | broker, credentials, base topic |
| `logging` | log file and log level |
| `rlc_percentages` | RLC current reduction percentages |
| `leds` | optional status LEDs |
| `buzzer` | optional startup/charging sounds |
| `home_assistant` | MQTT Discovery settings |
| `pv` | grid-power topic and surplus calculation |
| `web` | local dashboard host and port |

Important PV options:

| Field | Meaning |
| --- | --- |
| `pv.grid_power_topic` | MQTT topic for grid power |
| `pv.grid_power_export_negative` | `true` when export is negative |
| `pv.voltage` | voltage used for W-to-A calculation |
| `pv.phases` | number of charging phases used for calculation |
| `pv.min_current` | minimum current before charging may start |
| `pv.reserve_w` | surplus buffer kept unused |
| `pv.input_timeout_seconds` | maximum age of grid-power data |

Full option reference:

| Field | Unit | Purpose / default behavior |
| --- | --- | --- |
| `mqtt.broker_host` | host | MQTT broker hostname or IP |
| `mqtt.broker_port` | port | MQTT broker port, usually `1883` |
| `mqtt.client_id` | text | MQTT client identifier |
| `mqtt.username` | text/null | optional MQTT username |
| `mqtt.password` | text/null | optional MQTT password |
| `mqtt.base_topic` | topic | root topic, default `juicebooster` |
| `logging.file_path` | path | rotating log file path |
| `logging.level` | level | `INFO` for normal use, `DEBUG` for diagnostics |
| `rlc_percentages.rlc1` | percent | RLC1 current reduction |
| `rlc_percentages.rlc2` | percent | RLC2 current reduction |
| `rlc_percentages.rlc3` | percent | RLC3 current reduction |
| `rlc_percentages.rlc4` | percent | RLC4 current reduction |
| `leds.enabled` | boolean | enables optional GPIO status LEDs |
| `buzzer.enabled` | boolean | enables optional buzzer output |
| `buzzer.melodies.*.sequence` | Hz/ms | optional sound sequences |
| `home_assistant.discovery` | boolean | publishes MQTT Discovery entities |
| `home_assistant.discovery_prefix` | topic | usually `homeassistant` |
| `home_assistant.device_id` | text | stable HA device/entity prefix |
| `home_assistant.device_name` | text | visible HA device name, default `PV/MQTT Software for Charger Easy` |
| `pv.grid_power_topic` | topic | MQTT input for grid import/export |
| `pv.grid_power_export_negative` | boolean | `true` when export is negative |
| `pv.voltage` | V | W-to-A calculation voltage |
| `pv.phases` | count | charging phases used for W-to-A calculation |
| `pv.min_current` | A | minimum current required before charging starts |
| `pv.current_step` | A | current rounding step |
| `pv.reserve_w` | W | surplus kept unused as buffer |
| `pv.start_delay_seconds` | s | delay before PV charging starts |
| `pv.stop_delay_seconds` | s | delay before PV charging stops |
| `pv.input_timeout_seconds` | s | marks grid-power input stale |
| `web.enabled` | boolean | enables local dashboard/API |
| `web.host` | host | bind address; `0.0.0.0` means LAN reachable |
| `web.port` | port | dashboard port |
| `web.title` | text | browser/dashboard title, default `PV/MQTT Software for Charger Easy` |

## Hardware Overview

Required hardware:

- Raspberry Pi with GPIO and SPI
- MCP41xxx digital potentiometer, tested around MCP4161 behavior
- Juice Booster Easy / Juice CHARGER Easy control board
- GPIO wiring to CP state, DIP switches, current selector, RLC inputs
- optional LEDs and buzzer

Default BCM GPIO mapping:

| Function | GPIO |
| --- | ---: |
| CP input A | `6` |
| CP input B | `26` |
| hardware current selector | `18`, `24`, `23`, `25` |
| FreeCharge DIP1 | `22` |
| RLC DIP2 | `27` |
| RLC1..RLC4 | `21`, `20`, `16`, `5` |
| green LED | `12` |
| blue LED | `19` |
| buzzer | `13` |
| SPI CE0/MOSI/MISO/SCLK | `8`, `10`, `9`, `11` |

See [hardware documentation](docs/hardware.md).

## Operating Modes

| Mode | Behavior |
| --- | --- |
| `off` | Requests `0 A` |
| `instant` | Uses the configured instant current |
| `pv` | Calculates current from PV surplus |
| FreeCharge override | Physical DIP override; reported separately in state |

The selected software mode and hardware override are separate concepts. If the
FreeCharge DIP switch is active, the dashboard shows a hardware override badge.
Hardware limits still apply.

## Testing and Commissioning

1. Open the web dashboard.
2. Confirm MQTT connects and `juicebooster/availability` becomes `online`.
3. Confirm Home Assistant discovers the device.
4. Publish a test grid value:

   ```bash
   mosquitto_pub -h <mqtt-host> -t juicebooster/ha/gridPower -m -2000
   ```

5. Confirm dashboard values:

   ```text
   Grid Power: -2000 W
   PV Surplus: 1900 W
   ```

6. Test without a vehicle:

   ```text
   Target Current: 0 A
   Effective Current: 0 A
   Reason: vehicle_not_connected
   ```

7. Connect a vehicle and verify CP state:

   | CP state | Meaning |
   | --- | --- |
   | `A` | no vehicle |
   | `B` | vehicle connected |
   | `C` | vehicle ready / charging |
   | `E` / `F` | fault |

8. Select PV mode and verify current follows surplus.

## Troubleshooting

| Problem | Likely cause | Check |
| --- | --- | --- |
| PV data missing | No MQTT grid-power messages | Home Assistant automation and MQTT topic |
| PV surplus always `0` | Wrong sign convention | `grid_power_export_negative` |
| HA entities do not appear | Discovery not received | MQTT integration and `home_assistant.discovery` |
| Vehicle not detected | CP state remains `A` | plug, CP wiring, GPIO inputs |
| FreeCharge always active | DIP1 enabled or GPIO22 low | physical switch and wiring |
| Charging does not start | Surplus below minimum or stale data | `pv.min_current`, `reserve_w`, timeout |
| Current is capped | Hardware or RLC limit | hardware selector, DIP2, RLC inputs |

## FAQ

### Why is inverter power not used?

Inverter power only says what the inverter produces. It does not include house
load, battery charging/discharging, or the actual import/export at the grid
connection point.

### Why is grid power used?

Grid power is the real balance point. Negative grid power means the house is
exporting surplus; positive grid power means the house is importing.

### Why does charging not start below 6 A?

AC charging normally has a practical lower current limit around `6 A`. PV mode
waits until the calculated surplus can support at least `pv.min_current`.

### What does `reserve_w` do?

`reserve_w` keeps a small buffer unused so short household load changes do not
immediately pull power from the grid. With `grid_power_w = -2000 W` and
`reserve_w = 100 W`, the displayed surplus is `1900 W`.

### What is FreeCharge?

FreeCharge is a physical DIP switch override. The software reports it as
`hardware_override_free_charge`, but it does not replace hardware safety limits.

### What happens if MQTT data becomes stale?

PV mode requests `0 A`, sets `pv_input_stale: true`, and reports the stale
input through state and the dashboard.

## Documentation

- [Architecture](docs/architecture.md)
- [Home Assistant](docs/home-assistant.md)
- [MQTT](docs/mqtt.md)
- [Hardware](docs/hardware.md)
- [Security and Privacy](docs/security-privacy.md)

## Development

Install development dependencies:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py"
```

Run the fake dashboard without Raspberry Pi hardware:

```bash
python -m charger_easy.tools.fake_web --mode pv --current 10
```

Then open:

```text
http://127.0.0.1:8080/
```

Manual hardware test:

```bash
sudo python -m charger_easy.tools.set_current 10
```

Use `--eeprom` only if you intentionally want to write the non-volatile
MCP41xxx fallback register.

## Contributing

Contributions are welcome, especially:

- real dashboard screenshots
- wiring diagrams
- Home Assistant dashboard examples
- commissioning notes from other hardware revisions
- safer install/service packaging
- clearer documentation

Please keep hardware claims specific and tested. If a behavior is unclear,
document it as a TODO rather than implying support.

## Repository Metadata Suggestions

Suggested GitHub description:

```text
Unofficial Home Assistant and MQTT PV surplus controller software for Juice CHARGER Easy / Juice Booster Easy hardware.
```

Suggested GitHub topics:

```text
home-assistant
mqtt
solar
pv-surplus
ev-charging
raspberry-pi
juice-booster
wallbox
energy-management
smart-home
```

## License

This project is licensed under the Apache License 2.0.
Copyright (c) 2026 Jan Korte

You are free to use, modify, distribute, and commercialize this software in accordance with the terms of the Apache License 2.0.
See the LICENSE file for details.

## Disclaimer

This project changes charging behavior and interacts with mains-connected
charging hardware. Use it only if you understand the electrical and hardware
risks. The author assumes no liability for software errors, overloads, damage
to the Juice Booster, house installation, vehicles, Raspberry Pi hardware, or
other equipment. Use at your own risk.

All product and brand names are the property of their respective owners. This
project is an unofficial software fork/modification and is not affiliated with,
endorsed by, or sponsored by Juice Technology AG.

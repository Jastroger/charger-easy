# Hardware

This project controls charging hardware. Treat all hardware work as potentially
dangerous. Mains voltage work should only be done by qualified people.

The software can request current and read hardware states. It cannot validate
electrical safety.

Visual placeholder:

<!-- Replace with real wiring diagram: docs/images/wiring-overview.png -->

## Required Components

- Raspberry Pi with GPIO and SPI
- MCP41xxx digital potentiometer, tested around MCP4161 behavior
- Juice Booster Easy / Juice CHARGER Easy control board
- wiring for CP inputs, hardware current selector, DIP switches, and RLC inputs
- optional status LEDs
- optional buzzer

## Raspberry Pi Interfaces

Enable SPI:

```bash
sudo raspi-config
```

Use:

```text
Interface Options -> SPI -> Enable
```

The code opens:

```text
/dev/spidev0.0
```

## GPIO Mapping

BCM numbering:

| Function | GPIO | Direction | Pull / active state |
| --- | ---: | --- | --- |
| CP state input A | `6` | input | pull-down |
| CP state input B | `26` | input | pull-down |
| hardware current selector bit 0 | `18` | input | pull-up |
| hardware current selector bit 1 | `24` | input | pull-up |
| hardware current selector bit 2 | `23` | input | pull-up |
| hardware current selector legacy/reserved pin | `25` | input | pull-up |
| FreeCharge DIP1 | `22` | input | pull-up, `LOW` = ON |
| RLC DIP2 | `27` | input | pull-up, `LOW` = ON |
| RLC1 | `21` | input | pull-down, `HIGH` = active |
| RLC2 | `20` | input | pull-down, `HIGH` = active |
| RLC3 | `16` | input | pull-down, `HIGH` = active |
| RLC4 | `5` | input | pull-down, `HIGH` = active |
| green LED | `12` | output | software mode indicator |
| blue LED | `19` | output | RLC mode indicator |
| buzzer | `13` | PWM output | optional |
| SPI CE0 | `8` | SPI | chip select |
| SPI MOSI | `10` | SPI | data |
| SPI MISO | `9` | SPI | usually unused by writes |
| SPI SCLK | `11` | SPI | clock |

## Current Control

The service writes the MCP41xxx digital potentiometer over SPI.

Supported current curve:

```text
0 A, 6 A, 8 A, 10 A, 13 A, 16 A, 20 A, 25 A, 32 A
```

The requested current is converted to the next supported hardware value. The
effective current is capped by:

1. requested software current
2. hardware maximum selector
3. active RLC percentage

## FreeCharge / Hardware Override

DIP1 is read as the FreeCharge hardware override.

When DIP1 is ON:

- GPIO22 reads `LOW`
- the service reports `hardware_override_free_charge: true`
- selected software mode is still visible as `mode`
- effective mode becomes `hardware_override_free_charge`
- while a vehicle is connected, the request follows the hardware maximum

FreeCharge does not bypass hardware limits.

## RLC

DIP2 enables RLC reductions.

Default config:

```yaml
rlc_percentages:
  rlc1: 75
  rlc2: 50
  rlc3: 25
  rlc4: 0
```

If multiple RLC inputs are active, the strongest reduction wins.

## CP State

The controller maps CP inputs to:

| CP state | Meaning |
| --- | --- |
| `A` | no vehicle |
| `B` | vehicle connected |
| `C` | vehicle ready / charging |
| `E` / `F` | fault |

## Relay / Switching Note

The current code does not implement a separate relay output. If your hardware
build includes a relay, document the wiring and safety behavior separately.

TODO: add a tested wiring diagram for the exact hardware build.

## Recommended Test Procedure

Before connecting a vehicle:

1. Confirm SPI is enabled.
2. Start the service with mode `off`.
3. Confirm MQTT availability is `online`.
4. Confirm the dashboard loads.
5. Confirm CP state is `A`.
6. Publish test grid power:

   ```bash
   mosquitto_pub -h <mqtt-host> -t juicebooster/ha/gridPower -m -2000
   ```

7. Confirm PV surplus is displayed.
8. Confirm target and effective current remain `0 A` without a vehicle.
9. Toggle FreeCharge DIP and verify the dashboard badge changes.
10. Check RLC inputs if used.
11. Only then connect a vehicle and test low current first.

## What The Software Can Guarantee

The software can:

- clamp invalid current payloads
- request `0 A` in off mode
- stop PV charging when grid-power data is stale
- publish state and limit reasons
- keep RLC and hardware maximum in the effective-current calculation

The software cannot:

- verify your wiring
- verify mains protection
- guarantee the vehicle follows every request
- compensate for wrong hardware modifications
- make FreeCharge safe if hardware is wired incorrectly

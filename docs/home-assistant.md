# Home Assistant Setup

PV/MQTT Software for Charger Easy integrates with Home Assistant through MQTT.

Home Assistant needs two things:

1. The MQTT integration connected to the same broker as the Raspberry Pi.
2. An automation that publishes grid import/export power to the charger.

Visual placeholders:

<!-- Replace with real screenshot: docs/images/home-assistant-discovery.png -->
<!-- Replace with real screenshot: docs/images/web-ui.png -->

## MQTT Discovery

When `home_assistant.discovery: true`, the service publishes retained MQTT
Discovery payloads under:

```text
homeassistant/...
```

Default device:

```text
PV/MQTT Software for Charger Easy
```

Default device ID:

```text
juice_charger_easy
```

## Discovered Entities

Entity IDs can vary if Home Assistant resolves duplicates, but with the default
device ID they are typically:

| Entity | Purpose |
| --- | --- |
| `select.juice_charger_easy_mode` | select `off`, `pv`, or `instant` |
| `number.juice_charger_easy_instant_current` | instant charging current |
| `sensor.juice_charger_easy_cp_state` | CP state |
| `sensor.juice_charger_easy_grid_power_w` | grid power from MQTT input |
| `sensor.juice_charger_easy_pv_surplus_w` | calculated PV surplus |
| `sensor.juice_charger_easy_target_current_a` | requested current |
| `sensor.juice_charger_easy_effective_current_a` | effective current |
| `sensor.juice_charger_easy_hw_max_current` | hardware maximum current |
| `sensor.juice_charger_easy_rlc_percentage` | active RLC percentage |
| `sensor.juice_charger_easy_limit_reason` | reason for current decision |
| `binary_sensor.juice_charger_easy_vehicle_connected` | vehicle connected |
| `binary_sensor.juice_charger_easy_is_charging` | charging active |
| `binary_sensor.juice_charger_easy_hardware_override_free_charge` | FreeCharge DIP active |
| `binary_sensor.juice_charger_easy_pv_input_stale` | grid-power data stale |

## Required Grid Power Input

PV surplus charging needs grid power at the grid connection point.

For RCT Power setups, a good source is:

```text
sensor.rct_power_storage_grid_power
```

This represents actual import/export at the grid connection point. Inverter
power alone is not enough because it does not include house load or battery
behavior.

Default sign convention:

```text
positive = grid import
negative = grid export
```

## Publish Grid Power Automation

```yaml
alias: Charger Easy - Publish Grid Power
description: Publish grid import/export power for PV mode.
mode: restart
trigger:
  - platform: state
    entity_id: sensor.rct_power_storage_grid_power
  - platform: time_pattern
    seconds: "/15"
condition:
  - condition: template
    value_template: "{{ is_number(states('sensor.rct_power_storage_grid_power')) }}"
action:
  - action: mqtt.publish
    data:
      topic: "juicebooster/ha/gridPower"
      payload: "{{ states('sensor.rct_power_storage_grid_power') | float }}"
      qos: 0
      retain: false
```

## Example: Enable PV Mode When Surplus Is Available

This example is intentionally generic. Adjust the entity IDs and thresholds to
your installation.

```yaml
alias: Charger Easy - Auto PV Mode
description: Switch to PV mode when export is stable, pause when surplus disappears.
mode: restart
trigger:
  - platform: numeric_state
    entity_id: sensor.rct_power_storage_grid_power
    below: -1600
    for: "00:02:00"
    id: surplus_available
  - platform: numeric_state
    entity_id: sensor.rct_power_storage_grid_power
    above: -200
    for: "00:05:00"
    id: surplus_gone
action:
  - choose:
      - conditions:
          - condition: trigger
            id: surplus_available
        sequence:
          - action: select.select_option
            target:
              entity_id: select.juice_charger_easy_mode
            data:
              option: pv
      - conditions:
          - condition: trigger
            id: surplus_gone
        sequence:
          - action: select.select_option
            target:
              entity_id: select.juice_charger_easy_mode
            data:
              option: off
```

## Example: Reduce Instant Current

If you use `instant` mode and want to reduce current when export disappears:

```yaml
alias: Charger Easy - Reduce Instant Current
mode: single
trigger:
  - platform: numeric_state
    entity_id: sensor.rct_power_storage_grid_power
    above: 0
    for: "00:02:00"
action:
  - action: number.set_value
    target:
      entity_id: number.juice_charger_easy_instant_current
    data:
      value: 6
```

## Dashboard Suggestions

Useful entities for a Home Assistant dashboard:

- mode select
- instant current number
- effective current
- target current
- PV surplus
- grid power
- vehicle connected
- CP state
- limit reason
- hardware FreeCharge override
- stale PV input

## Troubleshooting

| Problem | Check |
| --- | --- |
| Device does not appear | MQTT integration, discovery prefix, retained discovery topics |
| Entities appear but do not update | `juicebooster/state`, broker connection, service logs |
| PV surplus is wrong | grid-power sign convention and `pv.grid_power_export_negative` |
| PV mode does not start | `pv.min_current`, start delay, stale grid input |
| Mode select does nothing | `juicebooster/mode/set` topic and service logs |
| Hardware override is always on | FreeCharge DIP1 and GPIO22 wiring |

## Discovery Re-Publish

When Home Assistant publishes `online` to:

```text
homeassistant/status
```

the service republishes discovery payloads.

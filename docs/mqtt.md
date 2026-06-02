# MQTT Topics

Default base topic:

```text
juicebooster
```

The base topic is configured in:

```yaml
mqtt:
  base_topic: "juicebooster"
```

## Command Topics

| Topic | Payload | Purpose |
| --- | --- | --- |
| `juicebooster/mode/set` | `off`, `pv`, `instant` | selected software mode |
| `juicebooster/instantCurrent/set` | number, `0..32` | instant charging current in amps |
| `juicebooster/ha/gridPower` | number in watts | grid import/export for PV logic |
| `juicebooster/enable/set` | boolean | legacy: `true` -> `instant`, `false` -> `off` |
| `juicebooster/maxCurrent/set` | number, `0..32` | legacy: updates instant current |
| `homeassistant/status` | `online` | triggers discovery republish |

Boolean payloads for `enable/set` accept common values such as `true`, `false`,
`1`, `0`, `yes`, `no`, `on`, and `off`.

Current payloads may be integer or decimal values. Negative values are clamped
to `0`. Invalid values are ignored.

## State Topics

| Topic | Retained | Purpose |
| --- | --- | --- |
| `juicebooster/state` | yes | main JSON state |
| `juicebooster/debug/status` | yes | same JSON state, legacy debug topic |
| `juicebooster/mode` | yes | selected software mode |
| `juicebooster/instantCurrent` | yes | instant current setting |
| `juicebooster/availability` | yes | `online` / `offline` |
| `juicebooster/status` | yes | legacy CP state |
| `juicebooster/enabled` | yes | legacy enabled flag |
| `juicebooster/chargeCurrent` | yes | legacy effective current |

The service also sets an MQTT last will for:

```text
juicebooster/availability = offline
```

## Security Notes

MQTT is a control interface. Any client that can publish to command topics can
change charging mode/current or spoof the grid-power value used by PV mode.

Do not expose the broker to the internet. Use MQTT authentication and ACLs. At
minimum, restrict publish access to:

| Client | Should publish |
| --- | --- |
| Home Assistant | `juicebooster/ha/gridPower`, `juicebooster/mode/set`, `juicebooster/instantCurrent/set` |
| Controller software | `juicebooster/state`, `juicebooster/availability`, discovery and legacy state topics |

Retained state topics contain energy and vehicle status. Treat the broker as a
private system and clear retained messages before decommissioning hardware.

See [Security and Privacy](security-privacy.md).

## Home Assistant Discovery Topics

Discovery topics are retained and use:

```text
<discovery_prefix>/<component>/<device_id>_<object_suffix>/config
```

Defaults:

```yaml
home_assistant:
  discovery_prefix: "homeassistant"
  device_id: "juice_charger_easy"
```

Example:

```text
homeassistant/select/juice_charger_easy_mode/config
```

## Grid Power Payloads

Default PV input topic:

```text
juicebooster/ha/gridPower
```

Default sign convention:

```text
+1000 = importing 1000 W from the grid
-2000 = exporting 2000 W to the grid
```

Default config:

```yaml
pv:
  grid_power_export_negative: true
```

If your grid meter reports export as positive, set:

```yaml
pv:
  grid_power_export_negative: false
```

## State JSON Example

```json
{
  "mode": "pv",
  "effective_mode": "pv",
  "cp_state": "C",
  "vehicle_connected": true,
  "is_charging": true,
  "hardware_override_free_charge": false,
  "grid_power_w": -1850,
  "pv_surplus_w": 1750,
  "target_current_A": 8,
  "effective_current_A": 8,
  "instant_current_A": 10,
  "hw_max_current": 16,
  "rlc_percentage": 100,
  "rlc_limited_current_A": 16,
  "limit_reason": "pv_surplus_available",
  "pv_input_stale": false,
  "timestamp": "2026-05-27T12:00:00Z"
}
```

## Limit Reasons

Known values include:

| Value | Meaning |
| --- | --- |
| `off` | selected mode requests no charging |
| `instant` | instant mode controls current |
| `pv_surplus_available` | PV surplus can charge |
| `pv_waiting_start_delay` | surplus exists but start delay is running |
| `pv_waiting_stop_delay` | deficit exists but stop delay is running |
| `pv_waiting_for_surplus` | PV mode waits for enough surplus |
| `stale_grid_power` | grid-power input missing or too old |
| `vehicle_not_connected` | CP state is not connected |
| `hardware_override_free_charge` | physical FreeCharge override active |
| `hardware_limit` | hardware maximum capped current |
| `rlc_limit` | RLC reduction capped current |
| `hardware_or_rlc_limit` | effective current was capped |
| `not_started` | service has not produced a runtime state yet |

## MQTT Test Commands

Publish grid export:

```bash
mosquitto_pub -h <mqtt-host> -t juicebooster/ha/gridPower -m -2000
```

Select PV mode:

```bash
mosquitto_pub -h <mqtt-host> -t juicebooster/mode/set -m pv
```

Set instant current:

```bash
mosquitto_pub -h <mqtt-host> -t juicebooster/instantCurrent/set -m 10
```

Watch state:

```bash
mosquitto_sub -h <mqtt-host> -t juicebooster/state -v
```

## Troubleshooting

| Problem | Check |
| --- | --- |
| No state messages | broker host, credentials, service logs |
| Commands do nothing | base topic and payload spelling |
| PV data stale | publish `gridPower` more often than `input_timeout_seconds` |
| Discovery missing | retained discovery topics and `homeassistant/status` |
| Wrong surplus sign | `grid_power_export_negative` |

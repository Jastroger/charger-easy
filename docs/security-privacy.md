# Security and Privacy

PV/MQTT Software for Charger Easy is intended for a trusted local network. It
controls EV charging behavior and publishes household energy status, so treat
it like other home automation infrastructure.

## Main Risks

| Surface | Risk | Mitigation |
| --- | --- | --- |
| Web dashboard/API | anyone with network access can view state and send mode/current commands | trusted LAN/VPN only, firewall, reverse proxy with authentication |
| MQTT command topics | clients can change mode/current or spoof grid power | broker authentication, ACLs, no anonymous writes |
| MQTT retained state | retained messages reveal vehicle, charging, and energy status | private broker, clear retained messages before decommissioning |
| `config.yaml` | MQTT credentials are stored as plain text | restrictive file permissions, never commit real secrets |
| Logs | DEBUG logs include MQTT topics and payloads | use `INFO` normally, restrict log file access |
| Physical DIP switches | FreeCharge can override software mode | protect physical access, check dashboard hardware badge |

## Web Dashboard

The web server uses the local Python HTTP server and does not provide login,
sessions, CSRF protection, or TLS.

Default config:

```yaml
web:
  enabled: true
  host: "0.0.0.0"
  port: 8080
```

`0.0.0.0` binds to all interfaces. This is convenient during commissioning, but
it means any host that can reach the Raspberry Pi can open the dashboard and
call the API.

Recommended options:

- Keep the Raspberry Pi on a private LAN.
- Do not port-forward the dashboard.
- Use a VPN for remote access.
- If using a reverse proxy, set `web.host: "127.0.0.1"` and put
  authentication/TLS on the proxy.
- Restrict access with host firewall rules if the network is shared.

## MQTT

MQTT is the control plane. A client that can publish to command topics can
change charger behavior.

Important command topics:

```text
juicebooster/mode/set
juicebooster/instantCurrent/set
juicebooster/ha/gridPower
juicebooster/enable/set
juicebooster/maxCurrent/set
```

Use broker credentials and ACLs. A practical split is:

- Home Assistant may publish grid power and user commands.
- The charger may subscribe to command topics.
- The charger may publish state, availability, and discovery topics.
- Anonymous clients may not publish to `juicebooster/#`.

If MQTT crosses an untrusted network, use TLS or a VPN.

## Retained Messages

The service retains state and discovery messages so Home Assistant can recover
cleanly after restarts. Retained state may include:

- selected mode
- effective current
- vehicle connected/charging state
- grid power
- PV surplus
- CP state
- hardware override state

This can reveal presence and energy usage patterns. Keep the broker private.
Before handing over, selling, or repurposing the Raspberry Pi or broker, clear
retained topics under:

```text
juicebooster/#
homeassistant/.../juice_charger_easy.../config
```

## Config File Permissions

If `config.yaml` contains MQTT credentials, lock it down:

```bash
sudo chown root:root /opt/juice-charger/config.yaml
sudo chmod 600 /opt/juice-charger/config.yaml
```

Do not commit real broker hostnames, usernames, passwords, or private network
details.

## Logs

Normal operation should use:

```yaml
logging:
  level: "INFO"
```

`DEBUG` can be useful while commissioning, but it logs MQTT topics and payloads.
Review logs before sharing them publicly.

## Service User

The example systemd service runs as `root` because GPIO and SPI access are often
restricted on Raspberry Pi systems. This is simple and works, but it increases
the impact of any process compromise.

For production, consider a dedicated service user with only the permissions
needed for GPIO, SPI, config, and logs. If that is not practical, restrict
network access to the web dashboard and MQTT broker.

## Hardware Override

The FreeCharge DIP switch is a physical override. The dashboard reports it as
`hardware_override_free_charge`, but software mode `off` does not remove the
physical reality of that switch.

Protect physical access to the charger hardware and verify the hardware badge
during commissioning.

## Release Checklist

- Web dashboard is not exposed to the internet.
- MQTT broker requires authentication.
- MQTT ACLs restrict command topics.
- `config.yaml` has restrictive permissions.
- Log level is `INFO`.
- No real credentials are committed.
- Retained MQTT topics are cleared before ownership changes.
- Physical DIP switch state is verified.

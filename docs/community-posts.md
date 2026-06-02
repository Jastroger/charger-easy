# Community Launch Drafts

Use these as starting points when the project is ready for public feedback.

## GitHub Repository Description

```text
Home Assistant compatible PV surplus charging controller for Juice Booster Easy / Charger Easy using Raspberry Pi and MQTT.
```

## Suggested GitHub Topics

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

## Home Assistant Community Forum Draft

Title:

```text
Juice Charger Easy: PV surplus charging for Juice Booster Easy via MQTT
```

Post:

```text
Hi everyone,

I wanted PV surplus charging with my Juice Booster Easy / Juice CHARGER Easy
without replacing the whole charger, so I built a Raspberry Pi based controller
that integrates it with Home Assistant through MQTT.

What it does:

- publishes Home Assistant MQTT Discovery entities
- provides a local web dashboard
- supports off, instant and PV surplus modes
- reads grid import/export power from Home Assistant
- calculates PV surplus charging current locally
- keeps the existing hardware current selector and RLC limits active
- reports CP state, vehicle connected, effective current, target current,
  FreeCharge override and stale PV data

Hardware:

- Raspberry Pi
- MCP41xxx digital potentiometer, tested around MCP4161 behavior
- Juice Booster Easy / Juice CHARGER Easy control board
- GPIO/SPI wiring for CP state, current selector, DIP switches and RLC inputs

Home Assistant sees the charger as an MQTT Discovery device with a mode select,
instant-current control, current/power sensors and binary sensors.

GitHub:

[GitHub link placeholder]

Screenshots:

[dashboard screenshot placeholder]
[Home Assistant discovery screenshot placeholder]
[wiring overview placeholder]

I would be happy to get feedback from other Home Assistant users, especially
people with Juice Booster Easy hardware, RCT Power installations, or similar PV
surplus charging setups.
```

## Reddit r/homeassistant Draft

```text
I wanted PV surplus charging with my Juice Booster Easy without replacing the
whole charger, so I built this Raspberry Pi + MQTT controller for Home
Assistant.

It reads grid import/export power from HA, calculates PV surplus locally and
requests the matching charging current. The existing hardware current selector,
RLC limits and CP state stay active, so the software is not trying to replace
the charger safety hardware.

What is working:

- Home Assistant MQTT Discovery
- local web dashboard
- off / instant / PV modes
- PV surplus calculation from grid power
- FreeCharge hardware override reporting
- stale PV data detection
- CP state and current sensors

GitHub link:
[GitHub link placeholder]

I still need to add real screenshots and a proper wiring diagram, but the
service is running on real hardware now. Feedback from HA / EV charging people
would be very welcome.
```

## Short Project Blurb

```text
Juice Charger Easy turns a Juice Booster Easy / Juice CHARGER Easy setup into a
Home Assistant compatible PV surplus charger using a Raspberry Pi, MQTT and the
existing charger hardware limits.
```

## Screenshot Checklist

Before posting publicly, add:

- dashboard screenshot: `docs/images/dashboard.png`
- wiring overview: `docs/images/wiring-overview.png`
- Home Assistant Discovery screenshot: `docs/images/home-assistant-discovery.png`
- web UI screenshot: `docs/images/web-ui.png`

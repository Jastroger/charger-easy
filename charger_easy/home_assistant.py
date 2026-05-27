from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HomeAssistantConfig:
    discovery: bool = True
    discovery_prefix: str = "homeassistant"
    device_id: str = "juice_charger_easy"
    device_name: str = "Juice Charger Easy"


class HomeAssistantDiscovery:
    def __init__(self, config: HomeAssistantConfig, base_topic: str) -> None:
        self.config = config
        self.base_topic = base_topic

    def publish(self, client: Any) -> None:
        if not self.config.discovery:
            return
        for topic, payload in self.discovery_payloads():
            client.publish(topic, json.dumps(payload), retain=True)

    def discovery_payloads(self) -> list[tuple[str, dict[str, Any]]]:
        device = {
            "identifiers": [self.config.device_id],
            "name": self.config.device_name,
            "manufacturer": "Jastroger",
            "model": "Juice CHARGER Easy MQTT Controller",
        }
        availability_topic = f"{self.base_topic}/availability"
        state_topic = f"{self.base_topic}/state"

        entities: list[tuple[str, str, dict[str, Any]]] = [
            (
                "select",
                "mode",
                {
                    "name": "Modus",
                    "object_id": f"{self.config.device_id}_mode",
                    "unique_id": f"{self.config.device_id}_mode",
                    "state_topic": f"{self.base_topic}/mode",
                    "command_topic": f"{self.base_topic}/mode/set",
                    "options": ["off", "pv", "instant"],
                },
            ),
            (
                "number",
                "instant_current",
                {
                    "name": "Sofortladestrom",
                    "object_id": f"{self.config.device_id}_instant_current",
                    "unique_id": f"{self.config.device_id}_instant_current",
                    "state_topic": f"{self.base_topic}/instantCurrent",
                    "command_topic": f"{self.base_topic}/instantCurrent/set",
                    "min": 0,
                    "max": 32,
                    "step": 1,
                    "mode": "slider",
                    "unit_of_measurement": "A",
                    "device_class": "current",
                },
            ),
        ]

        sensors = {
            "cp_state": ("CP-State", None, None, "{{ value_json.cp_state }}"),
            "grid_power_w": ("Netzleistung", "W", "power", "{{ value_json.grid_power_w }}"),
            "pv_surplus_w": ("PV-Ueberschuss", "W", "power", "{{ value_json.pv_surplus_w }}"),
            "target_current_a": ("Zielstrom", "A", "current", "{{ value_json.target_current_A }}"),
            "effective_current_a": ("Effektiver Strom", "A", "current", "{{ value_json.effective_current_A }}"),
            "hw_max_current": ("Hardware-Maximum", "A", "current", "{{ value_json.hw_max_current }}"),
            "rlc_percentage": ("RLC-Begrenzung", "%", None, "{{ value_json.rlc_percentage }}"),
            "limit_reason": ("Limitierungsgrund", None, None, "{{ value_json.limit_reason }}"),
        }
        for key, (name, unit, device_class, template) in sensors.items():
            payload: dict[str, Any] = {
                "name": name,
                "object_id": f"{self.config.device_id}_{key}",
                "unique_id": f"{self.config.device_id}_{key}",
                "state_topic": state_topic,
                "value_template": template,
            }
            if unit:
                payload["unit_of_measurement"] = unit
            if device_class:
                payload["device_class"] = device_class
                payload["state_class"] = "measurement"
            entities.append(("sensor", key, payload))

        binary_sensors = {
            "vehicle_connected": "Fahrzeug verbunden",
            "is_charging": "Laedt",
            "hardware_override_free_charge": "Hardware-Override FreeCharge",
            "pv_input_stale": "PV-Daten veraltet",
        }
        for key, name in binary_sensors.items():
            entities.append(
                (
                    "binary_sensor",
                    key,
                    {
                        "name": name,
                        "object_id": f"{self.config.device_id}_{key}",
                        "unique_id": f"{self.config.device_id}_{key}",
                        "state_topic": state_topic,
                        "value_template": f"{{{{ 'ON' if value_json.{key} else 'OFF' }}}}",
                        "payload_on": "ON",
                        "payload_off": "OFF",
                    },
                )
            )

        payloads = []
        prefix = self.config.discovery_prefix.strip("/")
        for component, object_suffix, payload in entities:
            payload["availability_topic"] = availability_topic
            payload["device"] = device
            topic = f"{prefix}/{component}/{self.config.device_id}_{object_suffix}/config"
            payloads.append((topic, payload))
        return payloads

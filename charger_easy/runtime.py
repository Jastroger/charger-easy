from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from charger_easy.controller import JuiceBoosterControl


class ChargerRuntime:
    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        controller_factory: Callable[..., JuiceBoosterControl] = JuiceBoosterControl,
        mqtt_client_factory: Callable[[str], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.logger = logger
        self.controller_factory = controller_factory
        self.mqtt_client_factory = mqtt_client_factory
        self.sleep = sleep

        mqtt_config = config["mqtt"]
        self.mqtt_broker_host = mqtt_config["broker_host"]
        self.mqtt_broker_port = mqtt_config["broker_port"]
        self.mqtt_client_id = mqtt_config["client_id"]
        self.mqtt_username = mqtt_config.get("username")
        self.mqtt_password = mqtt_config.get("password")
        self.base_topic = mqtt_config["base_topic"]

        self.topic_enable_set = f"{self.base_topic}/enable/set"
        self.topic_max_current_set = f"{self.base_topic}/maxCurrent/set"
        self.topic_status_get = f"{self.base_topic}/status"
        self.topic_enabled_get = f"{self.base_topic}/enabled"
        self.topic_charge_current_get = f"{self.base_topic}/chargeCurrent"
        self.topic_debug_status = f"{self.base_topic}/debug/status"

        self.rlc_percentages = config.get("rlc_percentages", {})
        self.buzzer_config = config.get("buzzer", {"enabled": False, "melodies": {}})
        self.led_enabled = config.get("leds", {}).get("enabled", False)

        self.evcc_enabled = False
        self.evcc_target_current = 6.0
        self.was_charging = False
        self.last_cp_state: str | None = None

        self.controller: JuiceBoosterControl | None = None
        self.client: Any | None = None

    def on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        if self._is_success_rc(rc):
            self.logger.info("Erfolgreich mit MQTT-Broker verbunden.")
            client.subscribe([(self.topic_enable_set, 0), (self.topic_max_current_set, 0)])
            self.logger.info("Abonniert auf: %s, %s", self.topic_enable_set, self.topic_max_current_set)
            return
        self.logger.error("MQTT-Verbindung fehlgeschlagen mit Code: %s", rc)

    def on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        self.logger.debug("MQTT-Nachricht empfangen: Topic='%s', Payload='%s'", msg.topic, payload)

        if msg.topic == self.topic_enable_set:
            parsed_enable = self._parse_bool(payload)
            if parsed_enable is None:
                self.logger.warning("Ungueltiger Enable-Wert empfangen: %s", payload)
                return
            self.evcc_enabled = parsed_enable
            self.logger.info("EVCC Command: Charger %s.", "enabled" if self.evcc_enabled else "disabled")
            if not self.evcc_enabled and self.controller:
                self.controller.play_melody("stop_charging")
            return

        if msg.topic == self.topic_max_current_set:
            try:
                self.evcc_target_current = max(0.0, float(payload))
                self.logger.info("EVCC Command: Target current set to %sA.", self.evcc_target_current)
            except ValueError:
                self.logger.warning("Ungueltiger Wert fuer Ladestrom empfangen: %s", payload)

    def run(self) -> None:
        try:
            self.controller = self.controller_factory(
                rlc_percentages_from_config=self.rlc_percentages,
                buzzer_config=self.buzzer_config,
                led_enabled=self.led_enabled,
            )

            self.client = self._create_mqtt_client()
            if self.mqtt_username and self.mqtt_password:
                self.client.username_pw_set(self.mqtt_username, self.mqtt_password)

            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.connect(self.mqtt_broker_host, self.mqtt_broker_port, 60)
            self.client.loop_start()

            self.logger.info("Steuerung gestartet. Hauptschleife beginnt.")
            self._run_main_loop()
        except KeyboardInterrupt:
            self.logger.info("Programm wird durch Benutzer beendet.")
        except Exception:
            self.logger.exception("Ein unerwarteter Fehler ist aufgetreten")
        finally:
            self._cleanup()

    def _create_mqtt_client(self) -> Any:
        if self.mqtt_client_factory:
            return self.mqtt_client_factory(self.mqtt_client_id)

        import paho.mqtt.client as mqtt

        return mqtt.Client(client_id=self.mqtt_client_id)

    def _run_main_loop(self) -> None:
        while True:
            assert self.controller is not None
            free_charge_mode = self.controller.is_free_charging_enabled()
            cp_state = self.controller.get_cp_state()
            max_hw_current = self.controller.get_max_hardware_current()
            is_connected = cp_state in ["B", "C"]

            self.controller.led()
            self._handle_cp_state_change(cp_state)

            requested_current = self._resolve_requested_current(free_charge_mode, is_connected, max_hw_current)
            effective_current = self.controller.set_charge_current(requested_current)
            is_charging = effective_current > 0 and cp_state == "C"

            self._handle_charging_transition(is_charging)
            self._publish_status(cp_state, effective_current, is_charging, free_charge_mode, max_hw_current)

            self.was_charging = is_charging
            self.sleep(2)

    def _resolve_requested_current(self, free_charge_mode: bool, is_connected: bool, max_hw_current: int) -> float:
        if free_charge_mode and is_connected:
            return float(max_hw_current)
        if self.evcc_enabled and is_connected:
            return float(self.evcc_target_current)
        return 0.0

    def _handle_cp_state_change(self, cp_state: str) -> None:
        assert self.controller is not None
        if cp_state == self.last_cp_state:
            return

        if cp_state in ["B", "C"] and self.last_cp_state not in ["B", "C"]:
            self.logger.info("Fahrzeug verbunden (CP-State Wechsel von %s zu %s).", self.last_cp_state, cp_state)
            self.controller.play_melody("car_connected")
        elif cp_state == "A" and self.last_cp_state in ["B", "C"]:
            self.logger.info("Fahrzeug getrennt (CP-State Wechsel von %s zu %s).", self.last_cp_state, cp_state)
            self.controller.play_melody("stop_charging")

        self.last_cp_state = cp_state

    def _handle_charging_transition(self, is_charging: bool) -> None:
        assert self.controller is not None
        if is_charging and not self.was_charging:
            self.logger.info("Ladevorgang startet. Spiele Melodie 'start_charging'.")
            self.controller.play_melody("start_charging")
            return

        if not is_charging and self.was_charging:
            self.logger.info("Ladevorgang beendet. Spiele Melodie 'stop_charging'.")
            self.controller.play_melody("stop_charging")

    def _publish_status(
        self,
        cp_state: str,
        effective_current: float,
        is_charging: bool,
        free_charge_mode: bool,
        max_hw_current: int,
    ) -> None:
        assert self.client is not None
        assert self.controller is not None
        mode_status = "FreeCharge Mode" if free_charge_mode else "EVCC Control"
        rlc_percentage = self.controller.get_rlc_percentage()

        self.client.publish(self.topic_status_get, cp_state, retain=True)
        self.client.publish(self.topic_enabled_get, "true" if effective_current > 0 else "false", retain=True)
        self.client.publish(self.topic_charge_current_get, str(effective_current), retain=True)

        debug_payload = {
            "cp_state": cp_state,
            "mode_active": mode_status,
            "evcc_cmd_enabled": self.evcc_enabled,
            "evcc_target_current_cmd": self.evcc_target_current,
            "hw_max_current": max_hw_current,
            "rlc_percentage": rlc_percentage,
            "effective_current_A": effective_current,
            "is_charging": is_charging,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.client.publish(self.topic_debug_status, json.dumps(debug_payload), retain=True)

        self.logger.info(
            "Status: Mode=%s, CP=%s, HW-Max=%sA, RLC=%s%%, EVCC-Target=%sA, Effektiv=%.1fA",
            mode_status,
            cp_state,
            max_hw_current,
            rlc_percentage,
            self.evcc_target_current,
            effective_current,
        )

    def _cleanup(self) -> None:
        if self.client:
            try:
                if hasattr(self.client, "loop_stop"):
                    self.client.loop_stop()
                if not hasattr(self.client, "is_connected") or self.client.is_connected():
                    self.client.disconnect()
            except Exception:
                self.logger.exception("Fehler beim Trennen der MQTT-Verbindung")
        if self.controller:
            self.controller.cleanup()
        self.logger.info("Aufgeraeumt und beendet.")

    @staticmethod
    def _parse_bool(payload: str) -> bool | None:
        normalized = payload.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return None

    @staticmethod
    def _is_success_rc(rc: Any) -> bool:
        try:
            return int(rc) == 0
        except (TypeError, ValueError):
            return str(rc).lower() in {"0", "success"}


from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable

from charger_easy.controller import JuiceBoosterControl
from charger_easy.home_assistant import HomeAssistantConfig, HomeAssistantDiscovery
from charger_easy.pv import PvConfig, PvDecision, PvRegulator
from charger_easy.web import WebConfig, WebDashboardServer

VALID_MODES = {"off", "pv", "instant"}


class ChargerRuntime:
    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        controller_factory: Callable[..., JuiceBoosterControl] = JuiceBoosterControl,
        mqtt_client_factory: Callable[[str], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.logger = logger
        self.controller_factory = controller_factory
        self.mqtt_client_factory = mqtt_client_factory
        self.sleep = sleep
        self.time_fn = time_fn

        mqtt_config = config["mqtt"]
        self.mqtt_broker_host = mqtt_config["broker_host"]
        self.mqtt_broker_port = mqtt_config["broker_port"]
        self.mqtt_client_id = mqtt_config["client_id"]
        self.mqtt_username = mqtt_config.get("username")
        self.mqtt_password = mqtt_config.get("password")
        self.base_topic = mqtt_config["base_topic"]

        home_assistant_config = config["home_assistant"]
        pv_config = config["pv"]
        self.home_assistant_config = HomeAssistantConfig(
            discovery=home_assistant_config["discovery"],
            discovery_prefix=home_assistant_config["discovery_prefix"],
            device_id=home_assistant_config["device_id"],
            device_name=home_assistant_config["device_name"],
        )
        self.pv_config = PvConfig(
            grid_power_topic=pv_config["grid_power_topic"],
            grid_power_export_negative=pv_config["grid_power_export_negative"],
            voltage=pv_config["voltage"],
            phases=pv_config["phases"],
            min_current=pv_config["min_current"],
            current_step=pv_config["current_step"],
            reserve_w=pv_config["reserve_w"],
            start_delay_seconds=pv_config["start_delay_seconds"],
            stop_delay_seconds=pv_config["stop_delay_seconds"],
            input_timeout_seconds=pv_config["input_timeout_seconds"],
        )
        web_config = config["web"]
        self.web_config = WebConfig(
            enabled=web_config["enabled"],
            host=web_config["host"],
            port=web_config["port"],
            title=web_config["title"],
        )
        self.pv_regulator = PvRegulator(self.pv_config)
        self.home_assistant_discovery = HomeAssistantDiscovery(self.home_assistant_config, self.base_topic)

        self.topic_enable_set = f"{self.base_topic}/enable/set"
        self.topic_max_current_set = f"{self.base_topic}/maxCurrent/set"
        self.topic_status_get = f"{self.base_topic}/status"
        self.topic_enabled_get = f"{self.base_topic}/enabled"
        self.topic_charge_current_get = f"{self.base_topic}/chargeCurrent"
        self.topic_debug_status = f"{self.base_topic}/debug/status"

        self.topic_mode_set = f"{self.base_topic}/mode/set"
        self.topic_mode_get = f"{self.base_topic}/mode"
        self.topic_instant_current_set = f"{self.base_topic}/instantCurrent/set"
        self.topic_instant_current_get = f"{self.base_topic}/instantCurrent"
        self.topic_grid_power = self.pv_config.grid_power_topic
        self.topic_state = f"{self.base_topic}/state"
        self.topic_availability = f"{self.base_topic}/availability"
        self.topic_home_assistant_status = "homeassistant/status"

        self.rlc_percentages = config.get("rlc_percentages", {})
        self.buzzer_config = config.get("buzzer", {"enabled": False, "melodies": {}})
        self.led_enabled = config.get("leds", {}).get("enabled", False)

        self.mode = "off"
        self.instant_current = 6.0
        self.evcc_enabled = False
        self.evcc_target_current = self.instant_current
        self.was_charging = False
        self.last_cp_state: str | None = None
        self.last_effective_current = 0.0
        self.last_status: dict[str, Any] | None = None

        self.controller: JuiceBoosterControl | None = None
        self.client: Any | None = None
        self.web_server: WebDashboardServer | None = None
        self._state_lock = threading.RLock()

    def on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        if not self._is_success_rc(rc):
            self.logger.error("MQTT-Verbindung fehlgeschlagen mit Code: %s", rc)
            return

        self.logger.info("Erfolgreich mit MQTT-Broker verbunden.")
        client.subscribe(
            [
                (self.topic_enable_set, 0),
                (self.topic_max_current_set, 0),
                (self.topic_mode_set, 0),
                (self.topic_instant_current_set, 0),
                (self.topic_grid_power, 0),
                (self.topic_home_assistant_status, 0),
            ]
        )
        self.logger.info("MQTT-Topics abonniert.")
        client.publish(self.topic_availability, "online", retain=True)
        self._publish_static_state(client)
        self._publish_home_assistant_discovery(client)

    def on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        self.logger.debug("MQTT-Nachricht empfangen: Topic='%s', Payload='%s'", msg.topic, payload)

        if msg.topic == self.topic_home_assistant_status:
            if payload.lower() == "online":
                self._publish_home_assistant_discovery(client)
            return

        if msg.topic == self.topic_enable_set:
            parsed_enable = self._parse_bool(payload)
            if parsed_enable is None:
                self.logger.warning("Ungueltiger Enable-Wert empfangen: %s", payload)
                return
            self.set_mode("instant" if parsed_enable else "off", source="legacy")
            if not parsed_enable and self.controller:
                self.controller.play_melody("stop_charging")
            return

        if msg.topic == self.topic_mode_set:
            if not self.set_mode(payload, source="mqtt"):
                self.logger.warning("Ungueltiger Modus empfangen: %s", payload)
            return

        if msg.topic in {self.topic_max_current_set, self.topic_instant_current_set}:
            if not self.set_instant_current(payload, source="mqtt"):
                self.logger.warning("Ungueltiger Wert fuer Ladestrom empfangen: %s", payload)
            return

        if msg.topic == self.topic_grid_power:
            try:
                self.pv_regulator.update_grid_power(float(payload), self.time_fn())
            except ValueError:
                self.logger.warning("Ungueltige Netzleistung empfangen: %s", payload)

    def run(self) -> None:
        try:
            self.controller = self.controller_factory(
                rlc_percentages_from_config=self.rlc_percentages,
                buzzer_config=self.buzzer_config,
                led_enabled=self.led_enabled,
            )

            self.client = self._create_mqtt_client()
            if hasattr(self.client, "will_set"):
                self.client.will_set(self.topic_availability, "offline", retain=True)
            if self.mqtt_username and self.mqtt_password:
                self.client.username_pw_set(self.mqtt_username, self.mqtt_password)

            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.connect(self.mqtt_broker_host, self.mqtt_broker_port, 60)
            self.client.loop_start()
            self._start_web_server()

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

    def set_mode(self, requested_mode: str, source: str = "api") -> bool:
        mode = str(requested_mode).strip().lower()
        if mode not in VALID_MODES:
            return False
        with self._state_lock:
            self.mode = mode
            self.evcc_enabled = mode != "off"
            if mode != "pv":
                self.pv_regulator.reset()
        self.logger.info("Modus auf %s gesetzt (%s).", mode, source)
        self._publish_static_state()
        return True

    def set_instant_current(self, requested_current: Any, source: str = "api") -> bool:
        current = self._parse_current(requested_current)
        if current is None:
            return False
        current = min(32.0, current)
        with self._state_lock:
            self.instant_current = current
            self.evcc_target_current = current
        self.logger.info("Sofortladestrom auf %sA gesetzt (%s).", current, source)
        self._publish_static_state()
        return True

    def get_web_state(self) -> dict[str, Any]:
        with self._state_lock:
            state = dict(self.last_status or self._default_state())
            state["mode"] = self.mode
            state["instant_current_A"] = self.instant_current
            state["grid_power_w"] = self.pv_regulator.grid_power_w
            state["web"] = {
                "enabled": self.web_config.enabled,
                "host": self.web_config.host,
                "port": self.web_config.port,
            }
            state["topics"] = {
                "state": self.topic_state,
                "mode_set": self.topic_mode_set,
                "instant_current_set": self.topic_instant_current_set,
                "grid_power": self.topic_grid_power,
            }
            state["pv_settings"] = {
                "voltage": self.pv_config.voltage,
                "phases": self.pv_config.phases,
                "min_current": self.pv_config.min_current,
                "reserve_w": self.pv_config.reserve_w,
                "start_delay_seconds": self.pv_config.start_delay_seconds,
                "stop_delay_seconds": self.pv_config.stop_delay_seconds,
                "input_timeout_seconds": self.pv_config.input_timeout_seconds,
            }
            return state

    def _default_state(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "effective_mode": self.mode,
            "cp_state": "unknown",
            "vehicle_connected": False,
            "is_charging": False,
            "hardware_override_free_charge": False,
            "grid_power_w": self.pv_regulator.grid_power_w,
            "pv_surplus_w": None,
            "target_current_A": 0.0,
            "effective_current_A": self.last_effective_current,
            "instant_current_A": self.instant_current,
            "hw_max_current": None,
            "rlc_percentage": None,
            "rlc_limited_current_A": None,
            "limit_reason": "not_started",
            "pv_input_stale": self.pv_regulator.grid_power_w is None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _run_main_loop(self) -> None:
        while True:
            self._run_once()
            self.sleep(2)

    def _run_once(self) -> dict[str, Any]:
        assert self.controller is not None
        free_charge_mode = self.controller.is_free_charging_enabled()
        cp_state = self.controller.get_cp_state()
        max_hw_current = self.controller.get_max_hardware_current()
        rlc_percentage = self.controller.get_rlc_percentage()
        is_connected = cp_state in ["B", "C"]

        self.controller.led()
        self._handle_cp_state_change(cp_state)

        requested_current, control_reason, pv_decision = self._resolve_requested_current(
            free_charge_mode=free_charge_mode,
            is_connected=is_connected,
            max_hw_current=max_hw_current,
        )
        effective_current = self.controller.set_charge_current(requested_current)
        is_charging = effective_current > 0 and cp_state == "C"
        limit_reason = self._resolve_limit_reason(requested_current, effective_current, max_hw_current, rlc_percentage)
        if limit_reason == "none":
            limit_reason = control_reason

        self._handle_charging_transition(is_charging)
        state = self._build_state(
            cp_state=cp_state,
            is_connected=is_connected,
            is_charging=is_charging,
            free_charge_mode=free_charge_mode,
            max_hw_current=max_hw_current,
            rlc_percentage=rlc_percentage,
            requested_current=requested_current,
            effective_current=effective_current,
            limit_reason=limit_reason,
            pv_decision=pv_decision,
        )
        self._publish_status(state)

        with self._state_lock:
            self.was_charging = is_charging
            self.last_effective_current = effective_current
            self.last_status = state
        return state

    def _resolve_requested_current(
        self,
        free_charge_mode: bool,
        is_connected: bool,
        max_hw_current: int,
    ) -> tuple[float, str, PvDecision | None]:
        if not is_connected:
            pv_decision = self.pv_regulator.decide(
                self.time_fn(),
                current_charging_current=self.last_effective_current,
            )
            return 0.0, "vehicle_not_connected", pv_decision

        if free_charge_mode:
            self.pv_regulator.reset()
            return float(max_hw_current), "hardware_override_free_charge", None

        if self.mode == "off":
            self.pv_regulator.reset()
            return 0.0, "off", None

        if self.mode == "instant":
            self.pv_regulator.reset()
            return self.instant_current, "instant", None

        pv_decision = self.pv_regulator.decide(self.time_fn(), current_charging_current=self.last_effective_current)
        return pv_decision.requested_current, pv_decision.reason, pv_decision

    def _resolve_limit_reason(
        self,
        requested_current: float,
        effective_current: float,
        max_hw_current: int,
        rlc_percentage: float,
    ) -> str:
        if requested_current <= effective_current:
            return "none"
        rlc_limited_current = max_hw_current * (rlc_percentage / 100.0)
        if rlc_percentage < 100 and effective_current <= rlc_limited_current:
            return "rlc_limit"
        if requested_current > max_hw_current:
            return "hardware_limit"
        return "hardware_or_rlc_limit"

    def _build_state(
        self,
        cp_state: str,
        is_connected: bool,
        is_charging: bool,
        free_charge_mode: bool,
        max_hw_current: int,
        rlc_percentage: float,
        requested_current: float,
        effective_current: float,
        limit_reason: str,
        pv_decision: PvDecision | None,
    ) -> dict[str, Any]:
        grid_power_w = self.pv_regulator.grid_power_w
        pv_surplus_w = pv_decision.pv_surplus_w if pv_decision else None
        pv_input_stale = bool(pv_decision.input_stale) if pv_decision else self.pv_regulator.grid_power_w is None
        effective_mode = "hardware_override_free_charge" if free_charge_mode else self.mode
        return {
            "mode": self.mode,
            "effective_mode": effective_mode,
            "cp_state": cp_state,
            "vehicle_connected": is_connected,
            "is_charging": is_charging,
            "hardware_override_free_charge": free_charge_mode,
            "grid_power_w": grid_power_w,
            "pv_surplus_w": pv_surplus_w,
            "target_current_A": requested_current,
            "effective_current_A": effective_current,
            "instant_current_A": self.instant_current,
            "hw_max_current": max_hw_current,
            "rlc_percentage": rlc_percentage,
            "rlc_limited_current_A": max_hw_current * (rlc_percentage / 100.0),
            "limit_reason": limit_reason,
            "pv_input_stale": pv_input_stale,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

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

    def _publish_status(self, state: dict[str, Any]) -> None:
        assert self.client is not None
        payload = json.dumps(state)

        self.client.publish(self.topic_status_get, state["cp_state"], retain=True)
        self.client.publish(self.topic_enabled_get, "true" if state["effective_current_A"] > 0 else "false", retain=True)
        self.client.publish(self.topic_charge_current_get, str(state["effective_current_A"]), retain=True)
        self.client.publish(self.topic_mode_get, self.mode, retain=True)
        self.client.publish(self.topic_instant_current_get, str(self.instant_current), retain=True)
        self.client.publish(self.topic_state, payload, retain=True)
        self.client.publish(self.topic_debug_status, payload, retain=True)

        self.logger.info(
            "Status: Mode=%s, Effektiv=%s, CP=%s, HW-Max=%sA, RLC=%s%%, Grund=%s",
            state["effective_mode"],
            state["effective_current_A"],
            state["cp_state"],
            state["hw_max_current"],
            state["rlc_percentage"],
            state["limit_reason"],
        )

    def _publish_static_state(self, client: Any | None = None) -> None:
        target_client = client or self.client
        if not target_client:
            return
        target_client.publish(self.topic_mode_get, self.mode, retain=True)
        target_client.publish(self.topic_instant_current_get, str(self.instant_current), retain=True)

    def _publish_home_assistant_discovery(self, client: Any | None = None) -> None:
        target_client = client or self.client
        if not target_client:
            return
        self.home_assistant_discovery.publish(target_client)

    def _start_web_server(self) -> None:
        if not self.web_config.enabled:
            return
        self.web_server = WebDashboardServer(self, self.web_config, self.logger)
        self.web_server.start()

    def _cleanup(self) -> None:
        if self.web_server:
            try:
                self.web_server.stop()
            except Exception:
                self.logger.exception("Fehler beim Stoppen der Webansicht")
        if self.client:
            try:
                self.client.publish(self.topic_availability, "offline", retain=True)
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
    def _parse_current(payload: Any) -> float | None:
        try:
            return max(0.0, float(payload))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_success_rc(rc: Any) -> bool:
        try:
            return int(rc) == 0
        except (TypeError, ValueError):
            return str(rc).lower() in {"0", "success"}

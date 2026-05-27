import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler

import paho.mqtt.client as mqtt
import yaml

from juice_booster_control import JuiceBoosterControl

CONFIG_PATH = "/opt/juice-charger/config.yaml"


def load_config(config_path: str) -> dict:
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            return yaml.safe_load(config_file)
    except FileNotFoundError:
        print(f"Fehler: Konfigurationsdatei '{config_path}' nicht gefunden.", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as error:
        print(f"Fehler beim Parsen der Konfigurationsdatei '{config_path}': {error}", file=sys.stderr)
        sys.exit(1)


def configure_logger(config: dict) -> logging.Logger:
    log_level_str = config["logging"].get("level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger("mqtt_client_logger")
    logger.setLevel(log_level)
    logger.handlers.clear()

    log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = RotatingFileHandler(config["logging"]["file_path"], maxBytes=10 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(log_formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


class ChargerRuntime:
    def __init__(self, config: dict, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

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
        self.evcc_target_current = 6
        self.was_charging = False
        self.last_cp_state = None

        self.controller = None
        self.client = None

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info("Erfolgreich mit MQTT-Broker verbunden.")
            client.subscribe([(self.topic_enable_set, 0), (self.topic_max_current_set, 0)])
            self.logger.info("Abonniert auf: %s, %s", self.topic_enable_set, self.topic_max_current_set)
            return
        self.logger.error("MQTT-Verbindung fehlgeschlagen mit Code: %s", rc)

    def on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8")
        self.logger.debug("MQTT-Nachricht empfangen: Topic='%s', Payload='%s'", msg.topic, payload)

        if msg.topic == self.topic_enable_set:
            self.evcc_enabled = payload.lower() == "true"
            self.logger.info("EVCC Command: Charger %s.", "enabled" if self.evcc_enabled else "disabled")
            if not self.evcc_enabled:
                self.controller.play_melody("stop_charging")
            return

        if msg.topic == self.topic_max_current_set:
            try:
                self.evcc_target_current = int(float(payload))
                self.logger.info("EVCC Command: Target current set to %sA.", self.evcc_target_current)
            except ValueError:
                self.logger.warning("Ungueltiger Wert fuer Ladestrom empfangen: %s", payload)

    def run(self) -> None:
        try:
            self.controller = JuiceBoosterControl(
                rlc_percentages_from_config=self.rlc_percentages,
                buzzer_config=self.buzzer_config,
                led_enabled=self.led_enabled,
            )

            self.client = mqtt.Client(client_id=self.mqtt_client_id)
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

    def _run_main_loop(self) -> None:
        while True:
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
            time.sleep(2)

    def _resolve_requested_current(self, free_charge_mode: bool, is_connected: bool, max_hw_current: int) -> float:
        if free_charge_mode and is_connected:
            return float(max_hw_current)
        if self.evcc_enabled and is_connected:
            return float(self.evcc_target_current)
        return 0.0

    def _handle_cp_state_change(self, cp_state: str) -> None:
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
        mode_status = "FreeCharge Mode" if free_charge_mode else "EVCC Control"

        self.client.publish(self.topic_status_get, cp_state, retain=True)
        self.client.publish(self.topic_enabled_get, "true" if effective_current > 0 else "false", retain=True)
        self.client.publish(self.topic_charge_current_get, str(effective_current), retain=True)

        debug_payload = {
            "cp_state": cp_state,
            "mode_active": mode_status,
            "evcc_cmd_enabled": self.evcc_enabled,
            "evcc_target_current_cmd": self.evcc_target_current,
            "hw_max_current": max_hw_current,
            "rlc_percentage": self.controller.get_rlc_percentage(),
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
            self.controller.get_rlc_percentage(),
            self.evcc_target_current,
            effective_current,
        )

    def _cleanup(self) -> None:
        if self.client and self.client.is_connected():
            self.client.loop_stop()
            self.client.disconnect()
        if self.controller:
            self.controller.cleanup()
        self.logger.info("Aufgeraeumt und beendet.")


def main() -> None:
    config = load_config(CONFIG_PATH)
    logger = configure_logger(config)
    runtime = ChargerRuntime(config=config, logger=logger)
    runtime.run()


if __name__ == "__main__":
    main()

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Mapping

DEFAULT_CONFIG_PATH = "/opt/juice-charger/config.yaml"
ENV_CONFIG_PATH = "CHARGER_EASY_CONFIG"

DEFAULT_CONFIG: dict[str, Any] = {
    "mqtt": {
        "broker_host": "mqtt.local",
        "broker_port": 1883,
        "client_id": "ChargerEasyPi",
        "username": None,
        "password": None,
        "base_topic": "juicebooster",
    },
    "logging": {
        "file_path": "/opt/juice-charger/charger.log",
        "level": "INFO",
    },
    "rlc_percentages": {
        "rlc1": 75,
        "rlc2": 50,
        "rlc3": 25,
        "rlc4": 0,
    },
    "leds": {
        "enabled": False,
    },
    "buzzer": {
        "enabled": False,
        "melodies": {},
    },
    "home_assistant": {
        "discovery": True,
        "discovery_prefix": "homeassistant",
        "device_id": "juice_charger_easy",
        "device_name": "PV/MQTT Software for Charger Easy",
    },
    "pv": {
        "grid_power_topic": None,
        "grid_power_export_negative": True,
        "voltage": 230.0,
        "phases": 1,
        "min_current": 6.0,
        "current_step": 1.0,
        "reserve_w": 100.0,
        "start_delay_seconds": 60.0,
        "stop_delay_seconds": 180.0,
        "input_timeout_seconds": 60.0,
    },
    "web": {
        "enabled": True,
        "host": "0.0.0.0",
        "port": 8080,
        "title": "PV/MQTT Software for Charger Easy",
    },
}

KNOWN_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
KNOWN_RLC_KEYS = {"rlc1", "rlc2", "rlc3", "rlc4"}


class ConfigError(ValueError):
    """Raised when the charger configuration cannot be loaded or validated."""


def resolve_config_path(cli_path: str | None = None) -> str:
    return cli_path or os.environ.get(ENV_CONFIG_PATH) or DEFAULT_CONFIG_PATH


def load_config(config_path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as error:
        raise ConfigError("PyYAML ist nicht installiert. Installiere die Abhaengigkeiten aus requirements.txt.") from error

    path = Path(config_path)
    try:
        with path.open("r", encoding="utf-8") as config_file:
            raw_config = yaml.safe_load(config_file)
    except FileNotFoundError as error:
        raise ConfigError(f"Konfigurationsdatei '{path}' nicht gefunden.") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"Fehler beim Parsen der Konfigurationsdatei '{path}': {error}") from error

    return normalize_config(raw_config)


def normalize_config(raw_config: Any) -> dict[str, Any]:
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise ConfigError("Die Konfiguration muss ein YAML-Objekt sein.")

    config = _deep_merge(DEFAULT_CONFIG, raw_config)
    _normalize_mqtt(config["mqtt"])
    _normalize_logging(config["logging"])
    _normalize_rlc_percentages(config["rlc_percentages"])
    _normalize_leds(config["leds"])
    _normalize_buzzer(config["buzzer"])
    _normalize_home_assistant(config["home_assistant"])
    _normalize_pv(config["pv"], config["mqtt"]["base_topic"])
    _normalize_web(config["web"])
    return config


def _deep_merge(defaults: Mapping[str, Any], values: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(defaults))
    for key, value in values.items():
        if isinstance(result.get(key), dict) and isinstance(value, Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _normalize_mqtt(mqtt_config: dict[str, Any]) -> None:
    mqtt_config["broker_host"] = _require_string(mqtt_config.get("broker_host"), "mqtt.broker_host")
    mqtt_config["client_id"] = _require_string(mqtt_config.get("client_id"), "mqtt.client_id")
    mqtt_config["base_topic"] = _require_string(mqtt_config.get("base_topic"), "mqtt.base_topic").strip("/")
    if not mqtt_config["base_topic"]:
        raise ConfigError("mqtt.base_topic darf nicht leer sein.")

    try:
        port = int(mqtt_config.get("broker_port"))
    except (TypeError, ValueError) as error:
        raise ConfigError("mqtt.broker_port muss eine Zahl sein.") from error
    if not 1 <= port <= 65535:
        raise ConfigError("mqtt.broker_port muss zwischen 1 und 65535 liegen.")
    mqtt_config["broker_port"] = port

    mqtt_config["username"] = _optional_string(mqtt_config.get("username"), "mqtt.username")
    mqtt_config["password"] = _optional_string(mqtt_config.get("password"), "mqtt.password")


def _normalize_logging(logging_config: dict[str, Any]) -> None:
    logging_config["file_path"] = _require_string(logging_config.get("file_path"), "logging.file_path")
    level = _require_string(logging_config.get("level"), "logging.level").upper()
    if level not in KNOWN_LOG_LEVELS:
        raise ConfigError(f"logging.level muss einer von {sorted(KNOWN_LOG_LEVELS)} sein.")
    logging_config["level"] = level


def _normalize_rlc_percentages(rlc_percentages: dict[str, Any]) -> None:
    if not isinstance(rlc_percentages, dict):
        raise ConfigError("rlc_percentages muss ein YAML-Objekt sein.")

    for key, value in list(rlc_percentages.items()):
        if key not in KNOWN_RLC_KEYS:
            continue
        try:
            percentage = float(value)
        except (TypeError, ValueError) as error:
            raise ConfigError(f"rlc_percentages.{key} muss eine Zahl sein.") from error
        if not 0 <= percentage <= 100:
            raise ConfigError(f"rlc_percentages.{key} muss zwischen 0 und 100 liegen.")
        rlc_percentages[key] = int(percentage) if percentage.is_integer() else percentage


def _normalize_leds(led_config: dict[str, Any]) -> None:
    if not isinstance(led_config, dict):
        raise ConfigError("leds muss ein YAML-Objekt sein.")
    led_config["enabled"] = _as_bool(led_config.get("enabled", False), "leds.enabled")


def _normalize_buzzer(buzzer_config: dict[str, Any]) -> None:
    if not isinstance(buzzer_config, dict):
        raise ConfigError("buzzer muss ein YAML-Objekt sein.")
    buzzer_config["enabled"] = _as_bool(buzzer_config.get("enabled", False), "buzzer.enabled")
    melodies = buzzer_config.get("melodies", {})
    if melodies is None:
        melodies = {}
    if not isinstance(melodies, dict):
        raise ConfigError("buzzer.melodies muss ein YAML-Objekt sein.")
    buzzer_config["melodies"] = melodies


def _normalize_home_assistant(home_assistant_config: dict[str, Any]) -> None:
    if not isinstance(home_assistant_config, dict):
        raise ConfigError("home_assistant muss ein YAML-Objekt sein.")
    home_assistant_config["discovery"] = _as_bool(
        home_assistant_config.get("discovery", True), "home_assistant.discovery"
    )
    home_assistant_config["discovery_prefix"] = _require_string(
        home_assistant_config.get("discovery_prefix"), "home_assistant.discovery_prefix"
    ).strip("/")
    if not home_assistant_config["discovery_prefix"]:
        raise ConfigError("home_assistant.discovery_prefix darf nicht leer sein.")
    home_assistant_config["device_id"] = _require_string(
        home_assistant_config.get("device_id"), "home_assistant.device_id"
    )
    home_assistant_config["device_name"] = _require_string(
        home_assistant_config.get("device_name"), "home_assistant.device_name"
    )


def _normalize_pv(pv_config: dict[str, Any], base_topic: str) -> None:
    if not isinstance(pv_config, dict):
        raise ConfigError("pv muss ein YAML-Objekt sein.")

    grid_power_topic = pv_config.get("grid_power_topic")
    if grid_power_topic in (None, ""):
        grid_power_topic = f"{base_topic}/ha/gridPower"
    pv_config["grid_power_topic"] = _require_string(grid_power_topic, "pv.grid_power_topic").strip("/")
    if not pv_config["grid_power_topic"]:
        raise ConfigError("pv.grid_power_topic darf nicht leer sein.")

    pv_config["grid_power_export_negative"] = _as_bool(
        pv_config.get("grid_power_export_negative", True), "pv.grid_power_export_negative"
    )
    pv_config["voltage"] = _positive_float(pv_config.get("voltage"), "pv.voltage")
    pv_config["phases"] = _int_between(pv_config.get("phases"), "pv.phases", 1, 3)
    pv_config["min_current"] = _positive_float(pv_config.get("min_current"), "pv.min_current")
    pv_config["current_step"] = _positive_float(pv_config.get("current_step"), "pv.current_step")
    pv_config["reserve_w"] = _non_negative_float(pv_config.get("reserve_w"), "pv.reserve_w")
    pv_config["start_delay_seconds"] = _non_negative_float(
        pv_config.get("start_delay_seconds"), "pv.start_delay_seconds"
    )
    pv_config["stop_delay_seconds"] = _non_negative_float(
        pv_config.get("stop_delay_seconds"), "pv.stop_delay_seconds"
    )
    pv_config["input_timeout_seconds"] = _positive_float(
        pv_config.get("input_timeout_seconds"), "pv.input_timeout_seconds"
    )


def _normalize_web(web_config: dict[str, Any]) -> None:
    if not isinstance(web_config, dict):
        raise ConfigError("web muss ein YAML-Objekt sein.")
    web_config["enabled"] = _as_bool(web_config.get("enabled", True), "web.enabled")
    web_config["host"] = _require_string(web_config.get("host"), "web.host")
    web_config["port"] = _int_between(web_config.get("port"), "web.port", 1, 65535)
    web_config["title"] = _require_string(web_config.get("title"), "web.title")


def _as_bool(value: Any, path: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ConfigError(f"{path} muss true oder false sein.")


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} muss ein nicht-leerer Text sein.")
    return value.strip()


def _optional_string(value: Any, path: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{path} muss Text oder leer sein.")
    return value


def _positive_float(value: Any, path: str) -> float:
    number = _as_float(value, path)
    if number <= 0:
        raise ConfigError(f"{path} muss groesser als 0 sein.")
    return number


def _non_negative_float(value: Any, path: str) -> float:
    number = _as_float(value, path)
    if number < 0:
        raise ConfigError(f"{path} darf nicht negativ sein.")
    return number


def _as_float(value: Any, path: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"{path} muss eine Zahl sein.") from error


def _int_between(value: Any, path: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"{path} muss eine ganze Zahl sein.") from error
    if not minimum <= number <= maximum:
        raise ConfigError(f"{path} muss zwischen {minimum} und {maximum} liegen.")
    return number

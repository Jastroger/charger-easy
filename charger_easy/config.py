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
        "client_id": "JuiceBoosterPi",
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

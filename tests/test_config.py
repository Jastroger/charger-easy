from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from charger_easy.config import ConfigError, normalize_config, resolve_config_path


class ConfigTests(unittest.TestCase):
    def test_defaults_are_added(self) -> None:
        config = normalize_config({})

        self.assertEqual(config["mqtt"]["base_topic"], "juicebooster")
        self.assertEqual(config["mqtt"]["broker_port"], 1883)
        self.assertFalse(config["leds"]["enabled"])
        self.assertEqual(config["rlc_percentages"]["rlc2"], 50)

    def test_values_are_normalized(self) -> None:
        config = normalize_config(
            {
                "mqtt": {"base_topic": "/charger/", "broker_port": "1884", "username": ""},
                "logging": {"level": "debug"},
                "leds": {"enabled": "yes"},
            }
        )

        self.assertEqual(config["mqtt"]["base_topic"], "charger")
        self.assertEqual(config["mqtt"]["broker_port"], 1884)
        self.assertIsNone(config["mqtt"]["username"])
        self.assertEqual(config["logging"]["level"], "DEBUG")
        self.assertTrue(config["leds"]["enabled"])

    def test_invalid_rlc_percentage_is_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            normalize_config({"rlc_percentages": {"rlc1": 101}})

    def test_env_config_path_is_supported(self) -> None:
        with patch.dict(os.environ, {"CHARGER_EASY_CONFIG": "/tmp/charger.yaml"}):
            self.assertEqual(resolve_config_path(), "/tmp/charger.yaml")
            self.assertEqual(resolve_config_path("/custom.yaml"), "/custom.yaml")


if __name__ == "__main__":
    unittest.main()


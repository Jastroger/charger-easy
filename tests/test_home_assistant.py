from __future__ import annotations

import unittest

from charger_easy.home_assistant import HomeAssistantConfig, HomeAssistantDiscovery


class FakeClient:
    def __init__(self) -> None:
        self.published = []

    def publish(self, topic, payload, retain=False) -> None:
        self.published.append((topic, payload, retain))


class HomeAssistantDiscoveryTests(unittest.TestCase):
    def test_discovery_payloads_cover_controls_status_and_device(self) -> None:
        discovery = HomeAssistantDiscovery(HomeAssistantConfig(), "juicebooster")
        payloads = dict(discovery.discovery_payloads())

        self.assertIn("homeassistant/select/juice_charger_easy_mode/config", payloads)
        self.assertIn("homeassistant/number/juice_charger_easy_instant_current/config", payloads)
        self.assertIn("homeassistant/sensor/juice_charger_easy_effective_current_a/config", payloads)
        self.assertIn("homeassistant/binary_sensor/juice_charger_easy_is_charging/config", payloads)

        mode = payloads["homeassistant/select/juice_charger_easy_mode/config"]
        self.assertEqual(mode["command_topic"], "juicebooster/mode/set")
        self.assertEqual(mode["state_topic"], "juicebooster/mode")
        self.assertEqual(mode["options"], ["off", "pv", "instant"])
        self.assertEqual(mode["availability_topic"], "juicebooster/availability")
        self.assertEqual(mode["device"]["identifiers"], ["juice_charger_easy"])

    def test_publish_respects_discovery_flag(self) -> None:
        client = FakeClient()
        HomeAssistantDiscovery(HomeAssistantConfig(discovery=False), "juicebooster").publish(client)
        self.assertEqual(client.published, [])

        HomeAssistantDiscovery(HomeAssistantConfig(discovery=True), "juicebooster").publish(client)
        self.assertGreater(len(client.published), 0)
        self.assertTrue(all(retain for _, _, retain in client.published))


if __name__ == "__main__":
    unittest.main()


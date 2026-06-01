from __future__ import annotations

import json
import unittest
import urllib.request

from charger_easy.web import WebConfig, WebDashboardServer, render_dashboard


class FakeLogger:
    def info(self, *args, **kwargs) -> None: ...

    def debug(self, *args, **kwargs) -> None: ...

    def exception(self, *args, **kwargs) -> None: ...


class FakeRuntime:
    def __init__(self) -> None:
        self.mode = "off"
        self.instant_current = 6.0

    def get_web_state(self) -> dict:
        return {
            "mode": self.mode,
            "effective_mode": self.mode,
            "cp_state": "C",
            "vehicle_connected": True,
            "is_charging": self.mode != "off",
            "hardware_override_free_charge": False,
            "grid_power_w": -1200,
            "pv_surplus_w": 1100,
            "target_current_A": 6,
            "effective_current_A": 6,
            "instant_current_A": self.instant_current,
            "hw_max_current": 16,
            "rlc_percentage": 100,
            "limit_reason": "instant",
            "pv_input_stale": False,
            "timestamp": "2026-05-27T12:00:00Z",
        }

    def set_mode(self, mode: str, source: str = "web") -> bool:
        if mode not in {"off", "pv", "instant"}:
            return False
        self.mode = mode
        return True

    def set_instant_current(self, current, source: str = "web") -> bool:
        try:
            self.instant_current = float(current)
        except (TypeError, ValueError):
            return False
        return True


class WebDashboardTests(unittest.TestCase):
    def test_dashboard_contains_api_hooks(self) -> None:
        html = render_dashboard("Juice Charger Easy")

        self.assertIn("/api/state", html)
        self.assertIn("/api/mode", html)
        self.assertIn("/api/instant-current", html)
        self.assertIn("Juice Charger Easy", html)

    def test_dashboard_separates_selected_mode_from_hardware_override(self) -> None:
        html = render_dashboard("Juice Charger Easy")

        self.assertIn("hardwareOverrideNotice", html)
        self.assertIn("HW-FreeCharge", html)
        self.assertIn("reasonBadge", html)
        self.assertIn("metrics-grid", html)
        self.assertIn("Netzleistung", html)
        self.assertIn("PV-Überschuss", html)
        self.assertIn("Zielstrom", html)
        self.assertIn("Ladestrom", html)
        self.assertIn("const selectedMode = state.mode || state.effective_mode;", html)
        self.assertIn('label(MODE_LABELS, selectedMode)', html)
        self.assertNotIn("PV-Überschuss " + "gewählt", html)
        self.assertNotIn("PV-Überschuss ist " + "ausgewählt", html)
        self.assertNotIn("Der physische " + "Schalter kann", html)
        self.assertNotIn("FreeCharge ist aktiv", html)
        self.assertNotIn("Der physische " + "Schalter gibt das Laden direkt frei.", html)

    def test_server_serves_state_and_accepts_commands(self) -> None:
        runtime = FakeRuntime()
        server = WebDashboardServer(runtime, WebConfig(host="127.0.0.1", port=0), FakeLogger())
        server.start()
        try:
            base_url = server.url.rstrip("/")

            with urllib.request.urlopen(f"{base_url}/api/state", timeout=5) as response:
                state = json.loads(response.read().decode("utf-8"))
            self.assertEqual(state["mode"], "off")

            self._post_json(f"{base_url}/api/mode", {"mode": "pv"})
            self.assertEqual(runtime.mode, "pv")

            self._post_json(f"{base_url}/api/instant-current", {"current": 12})
            self.assertEqual(runtime.instant_current, 12)
        finally:
            server.stop()

    def _post_json(self, url: str, payload: dict) -> None:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()

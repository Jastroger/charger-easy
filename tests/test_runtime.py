from __future__ import annotations

import unittest
from types import SimpleNamespace

from charger_easy.config import normalize_config
from charger_easy.runtime import ChargerRuntime


class FakeLogger:
    def debug(self, *args, **kwargs) -> None: ...

    def info(self, *args, **kwargs) -> None: ...

    def warning(self, *args, **kwargs) -> None: ...

    def error(self, *args, **kwargs) -> None: ...

    def exception(self, *args, **kwargs) -> None: ...


class FakeClient:
    def __init__(self) -> None:
        self.subscriptions = []
        self.published = []
        self.connected = True

    def subscribe(self, subscriptions) -> None:
        self.subscriptions.extend(subscriptions)

    def publish(self, topic, payload, retain=False) -> None:
        self.published.append((topic, payload, retain))

    def is_connected(self) -> bool:
        return self.connected

    def loop_stop(self) -> None: ...

    def disconnect(self) -> None:
        self.connected = False


class FakeController:
    def __init__(self) -> None:
        self.free_charge = False
        self.cp_state = "C"
        self.max_current = 16
        self.rlc_percentage = 100.0
        self.currents = []

    def is_free_charging_enabled(self) -> bool:
        return self.free_charge

    def get_cp_state(self) -> str:
        return self.cp_state

    def get_max_hardware_current(self) -> int:
        return self.max_current

    def get_rlc_percentage(self) -> float:
        return self.rlc_percentage

    def led(self) -> None: ...

    def set_charge_current(self, requested_current: float) -> float:
        self.currents.append(requested_current)
        return min(requested_current, self.max_current * (self.rlc_percentage / 100.0))

    def play_melody(self, name: str) -> None: ...

    def cleanup(self) -> None: ...


class RuntimeTests(unittest.TestCase):
    def build_runtime(self, config=None, now: float = 0) -> ChargerRuntime:
        current_time = {"now": now}
        runtime = ChargerRuntime(
            normalize_config(config or {}),
            FakeLogger(),
            time_fn=lambda: current_time["now"],
        )
        runtime.test_time = current_time
        return runtime

    def msg(self, topic: str, payload: str) -> SimpleNamespace:
        return SimpleNamespace(topic=topic, payload=payload.encode("utf-8"))

    def test_topics_stay_compatible(self) -> None:
        runtime = self.build_runtime()

        self.assertEqual(runtime.topic_enable_set, "juicebooster/enable/set")
        self.assertEqual(runtime.topic_max_current_set, "juicebooster/maxCurrent/set")
        self.assertEqual(runtime.topic_status_get, "juicebooster/status")
        self.assertEqual(runtime.topic_enabled_get, "juicebooster/enabled")
        self.assertEqual(runtime.topic_charge_current_get, "juicebooster/chargeCurrent")
        self.assertEqual(runtime.topic_debug_status, "juicebooster/debug/status")
        self.assertEqual(runtime.topic_mode_set, "juicebooster/mode/set")
        self.assertEqual(runtime.topic_instant_current_set, "juicebooster/instantCurrent/set")
        self.assertEqual(runtime.topic_grid_power, "juicebooster/ha/gridPower")
        self.assertEqual(runtime.topic_state, "juicebooster/state")
        self.assertEqual(runtime.topic_availability, "juicebooster/availability")

    def test_current_payloads_accept_float_clamp_negative_and_ignore_invalid(self) -> None:
        runtime = self.build_runtime()

        runtime.on_message(None, None, self.msg(runtime.topic_max_current_set, "7.5"))
        self.assertEqual(runtime.instant_current, 7.5)

        runtime.on_message(None, None, self.msg(runtime.topic_max_current_set, "-3"))
        self.assertEqual(runtime.instant_current, 0.0)

        runtime.on_message(None, None, self.msg(runtime.topic_max_current_set, "nope"))
        self.assertEqual(runtime.instant_current, 0.0)

        runtime.on_message(None, None, self.msg(runtime.topic_instant_current_set, "10"))
        self.assertEqual(runtime.instant_current, 10.0)

    def test_enable_payloads_are_validated(self) -> None:
        runtime = self.build_runtime()

        runtime.on_message(None, None, self.msg(runtime.topic_enable_set, "true"))
        self.assertTrue(runtime.evcc_enabled)
        self.assertEqual(runtime.mode, "instant")

        runtime.on_message(None, None, self.msg(runtime.topic_enable_set, "invalid"))
        self.assertTrue(runtime.evcc_enabled)
        self.assertEqual(runtime.mode, "instant")

        runtime.on_message(None, None, self.msg(runtime.topic_enable_set, "false"))
        self.assertFalse(runtime.evcc_enabled)
        self.assertEqual(runtime.mode, "off")

    def test_mode_and_grid_power_commands_are_validated(self) -> None:
        runtime = self.build_runtime()
        runtime.on_message(None, None, self.msg(runtime.topic_mode_set, "pv"))
        self.assertEqual(runtime.mode, "pv")

        runtime.on_message(None, None, self.msg(runtime.topic_mode_set, "bad"))
        self.assertEqual(runtime.mode, "pv")

        runtime.on_message(None, None, self.msg(runtime.topic_grid_power, "-1500"))
        self.assertEqual(runtime.pv_regulator.grid_power_w, -1500)

    def test_connect_publishes_availability_static_state_and_discovery(self) -> None:
        runtime = self.build_runtime()
        client = FakeClient()

        runtime.on_connect(client, None, None, 0)

        published_topics = [topic for topic, _, _ in client.published]
        self.assertIn("juicebooster/availability", published_topics)
        self.assertIn("juicebooster/mode", published_topics)
        self.assertIn("homeassistant/select/juice_charger_easy_mode/config", published_topics)
        self.assertIn((runtime.topic_grid_power, 0), client.subscriptions)

    def test_run_once_publishes_rich_state_and_limits_current(self) -> None:
        runtime = self.build_runtime({"pv": {"start_delay_seconds": 0}})
        controller = FakeController()
        controller.rlc_percentage = 50.0
        runtime.controller = controller
        runtime.client = FakeClient()
        runtime.mode = "pv"
        runtime.on_message(None, None, self.msg(runtime.topic_grid_power, "-3000"))

        state = runtime._run_once()

        self.assertEqual(state["mode"], "pv")
        self.assertEqual(state["cp_state"], "C")
        self.assertTrue(state["vehicle_connected"])
        self.assertEqual(state["target_current_A"], 12)
        self.assertEqual(state["effective_current_A"], 8.0)
        self.assertEqual(state["limit_reason"], "rlc_limit")
        self.assertEqual(state["pv_surplus_w"], 2900.0)

        state_payloads = [payload for topic, payload, _ in runtime.client.published if topic == runtime.topic_state]
        self.assertTrue(state_payloads)
        self.assertIn('"hardware_override_free_charge": false', state_payloads[-1])

    def test_no_vehicle_keeps_current_zero_but_reports_pv_surplus(self) -> None:
        runtime = self.build_runtime(
            {
                "pv": {
                    "grid_power_export_negative": True,
                    "reserve_w": 100,
                    "voltage": 230,
                    "phases": 1,
                    "start_delay_seconds": 0,
                }
            }
        )
        controller = FakeController()
        controller.cp_state = "A"
        runtime.controller = controller
        runtime.client = FakeClient()
        runtime.mode = "pv"
        runtime.on_message(None, None, self.msg(runtime.topic_grid_power, "-2000"))

        state = runtime._run_once()

        self.assertEqual(state["effective_current_A"], 0.0)
        self.assertEqual(state["target_current_A"], 0.0)
        self.assertEqual(state["limit_reason"], "vehicle_not_connected")
        self.assertEqual(state["pv_surplus_w"], 1900.0)
        self.assertEqual(controller.currents, [0.0])

    def test_no_vehicle_reports_missing_pv_input_without_charging(self) -> None:
        runtime = self.build_runtime()
        controller = FakeController()
        controller.cp_state = "A"
        runtime.controller = controller
        runtime.client = FakeClient()
        runtime.mode = "pv"

        state = runtime._run_once()

        self.assertEqual(state["effective_current_A"], 0.0)
        self.assertEqual(state["target_current_A"], 0.0)
        self.assertEqual(state["limit_reason"], "vehicle_not_connected")
        self.assertTrue(state["pv_input_stale"])

    def test_no_vehicle_reports_stale_pv_input_without_charging(self) -> None:
        runtime = self.build_runtime({"pv": {"input_timeout_seconds": 10}}, now=0)
        controller = FakeController()
        controller.cp_state = "A"
        runtime.controller = controller
        runtime.client = FakeClient()
        runtime.mode = "pv"
        runtime.on_message(None, None, self.msg(runtime.topic_grid_power, "-2000"))
        runtime.test_time["now"] = 11

        state = runtime._run_once()

        self.assertEqual(state["effective_current_A"], 0.0)
        self.assertEqual(state["target_current_A"], 0.0)
        self.assertEqual(state["limit_reason"], "vehicle_not_connected")
        self.assertTrue(state["pv_input_stale"])

    def test_free_charge_dip_overrides_software_mode(self) -> None:
        runtime = self.build_runtime()
        controller = FakeController()
        controller.free_charge = True
        runtime.controller = controller
        runtime.client = FakeClient()
        runtime.mode = "off"

        state = runtime._run_once()

        self.assertEqual(state["effective_mode"], "hardware_override_free_charge")
        self.assertEqual(state["target_current_A"], 16.0)
        self.assertEqual(state["limit_reason"], "hardware_override_free_charge")


if __name__ == "__main__":
    unittest.main()

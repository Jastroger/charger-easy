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


class RuntimeTests(unittest.TestCase):
    def build_runtime(self) -> ChargerRuntime:
        return ChargerRuntime(normalize_config({}), FakeLogger())

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

    def test_current_payloads_accept_float_clamp_negative_and_ignore_invalid(self) -> None:
        runtime = self.build_runtime()

        runtime.on_message(None, None, self.msg(runtime.topic_max_current_set, "7.5"))
        self.assertEqual(runtime.evcc_target_current, 7.5)

        runtime.on_message(None, None, self.msg(runtime.topic_max_current_set, "-3"))
        self.assertEqual(runtime.evcc_target_current, 0.0)

        runtime.on_message(None, None, self.msg(runtime.topic_max_current_set, "nope"))
        self.assertEqual(runtime.evcc_target_current, 0.0)

    def test_enable_payloads_are_validated(self) -> None:
        runtime = self.build_runtime()

        runtime.on_message(None, None, self.msg(runtime.topic_enable_set, "true"))
        self.assertTrue(runtime.evcc_enabled)

        runtime.on_message(None, None, self.msg(runtime.topic_enable_set, "invalid"))
        self.assertTrue(runtime.evcc_enabled)

        runtime.on_message(None, None, self.msg(runtime.topic_enable_set, "false"))
        self.assertFalse(runtime.evcc_enabled)

    def test_requested_current_resolution(self) -> None:
        runtime = self.build_runtime()
        runtime.evcc_enabled = True
        runtime.evcc_target_current = 7.5

        self.assertEqual(runtime._resolve_requested_current(True, True, 16), 16.0)
        self.assertEqual(runtime._resolve_requested_current(False, True, 16), 7.5)
        self.assertEqual(runtime._resolve_requested_current(False, False, 16), 0.0)

        runtime.evcc_enabled = False
        self.assertEqual(runtime._resolve_requested_current(False, True, 16), 0.0)


if __name__ == "__main__":
    unittest.main()


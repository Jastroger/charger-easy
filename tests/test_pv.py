from __future__ import annotations

import unittest

from charger_easy.pv import PvConfig, PvRegulator


def config(**overrides) -> PvConfig:
    values = {
        "grid_power_topic": "juicebooster/ha/gridPower",
        "voltage": 230,
        "phases": 1,
        "min_current": 6,
        "current_step": 1,
        "reserve_w": 100,
        "start_delay_seconds": 60,
        "stop_delay_seconds": 180,
        "input_timeout_seconds": 60,
    }
    values.update(overrides)
    return PvConfig(**values)


class PvRegulatorTests(unittest.TestCase):
    def test_missing_or_stale_input_is_safe_zero(self) -> None:
        regulator = PvRegulator(config(input_timeout_seconds=10))

        decision = regulator.decide(now=0)
        self.assertEqual(decision.requested_current, 0)
        self.assertEqual(decision.reason, "stale_grid_power")
        self.assertTrue(decision.input_stale)

        regulator.update_grid_power(-2000, now=0)
        decision = regulator.decide(now=11)
        self.assertEqual(decision.requested_current, 0)
        self.assertEqual(decision.reason, "stale_grid_power")
        self.assertTrue(decision.input_stale)

    def test_surplus_starts_after_delay_and_uses_one_amp_steps(self) -> None:
        regulator = PvRegulator(config())
        regulator.update_grid_power(-2000, now=0)

        decision = regulator.decide(now=0)
        self.assertEqual(decision.requested_current, 0)
        self.assertEqual(decision.reason, "pv_waiting_start_delay")

        decision = regulator.decide(now=60)
        self.assertEqual(decision.requested_current, 8)
        self.assertEqual(decision.reason, "pv_surplus_available")
        self.assertFalse(decision.input_stale)

    def test_deficit_stops_after_delay(self) -> None:
        regulator = PvRegulator(config(start_delay_seconds=0, stop_delay_seconds=180))
        regulator.update_grid_power(-2000, now=0)
        self.assertEqual(regulator.decide(now=0).requested_current, 8)

        regulator.update_grid_power(1000, now=1)
        decision = regulator.decide(now=1, current_charging_current=8)
        self.assertEqual(decision.requested_current, 8)
        self.assertEqual(decision.reason, "pv_waiting_stop_delay")

        regulator.update_grid_power(1000, now=182)
        decision = regulator.decide(now=182, current_charging_current=8)
        self.assertEqual(decision.requested_current, 0)
        self.assertEqual(decision.reason, "pv_waiting_for_surplus")

    def test_positive_export_sign_can_be_configured(self) -> None:
        regulator = PvRegulator(config(grid_power_export_negative=False, start_delay_seconds=0))
        regulator.update_grid_power(2000, now=0)

        decision = regulator.decide(now=0)

        self.assertEqual(decision.requested_current, 8)
        self.assertEqual(decision.pv_surplus_w, 1900)


if __name__ == "__main__":
    unittest.main()

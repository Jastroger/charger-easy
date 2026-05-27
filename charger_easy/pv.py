from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PvConfig:
    grid_power_topic: str
    grid_power_export_negative: bool = True
    voltage: float = 230.0
    phases: int = 1
    min_current: float = 6.0
    current_step: float = 1.0
    reserve_w: float = 100.0
    start_delay_seconds: float = 60.0
    stop_delay_seconds: float = 180.0
    input_timeout_seconds: float = 60.0


@dataclass(frozen=True)
class PvDecision:
    requested_current: float
    pv_surplus_w: float | None
    reason: str
    input_stale: bool


class PvRegulator:
    def __init__(self, config: PvConfig) -> None:
        self.config = config
        self.grid_power_w: float | None = None
        self.grid_power_updated_at: float | None = None
        self._surplus_started_at: float | None = None
        self._deficit_started_at: float | None = None
        self._last_requested_current = 0.0

    def update_grid_power(self, grid_power_w: float, now: float) -> None:
        self.grid_power_w = float(grid_power_w)
        self.grid_power_updated_at = now

    def decide(self, now: float, current_charging_current: float = 0.0) -> PvDecision:
        if self.grid_power_w is None or self.grid_power_updated_at is None:
            self._reset_timers()
            self._last_requested_current = 0.0
            return PvDecision(0.0, None, "stale_grid_power", True)

        age = now - self.grid_power_updated_at
        if age > self.config.input_timeout_seconds:
            self._reset_timers()
            self._last_requested_current = 0.0
            return PvDecision(0.0, self._calculate_surplus(current_charging_current), "stale_grid_power", True)

        pv_surplus_w = self._calculate_surplus(current_charging_current)
        available_current = self._round_down_current(pv_surplus_w / self._watts_per_amp())

        if available_current >= self.config.min_current:
            self._deficit_started_at = None
            if self._surplus_started_at is None:
                self._surplus_started_at = now

            if self._last_requested_current <= 0 and now - self._surplus_started_at < self.config.start_delay_seconds:
                return PvDecision(0.0, pv_surplus_w, "pv_waiting_start_delay", False)

            self._last_requested_current = available_current
            return PvDecision(available_current, pv_surplus_w, "pv_surplus_available", False)

        self._surplus_started_at = None
        if self._last_requested_current > 0:
            if self._deficit_started_at is None:
                self._deficit_started_at = now
            if now - self._deficit_started_at < self.config.stop_delay_seconds:
                return PvDecision(self._last_requested_current, pv_surplus_w, "pv_waiting_stop_delay", False)

        self._deficit_started_at = None
        self._last_requested_current = 0.0
        return PvDecision(0.0, pv_surplus_w, "pv_waiting_for_surplus", False)

    def reset(self) -> None:
        self._reset_timers()
        self._last_requested_current = 0.0

    def _calculate_surplus(self, current_charging_current: float) -> float:
        assert self.grid_power_w is not None
        if self.config.grid_power_export_negative:
            grid_surplus_w = -self.grid_power_w
        else:
            grid_surplus_w = self.grid_power_w

        charging_power_w = max(0.0, current_charging_current) * self._watts_per_amp()
        return grid_surplus_w + charging_power_w - self.config.reserve_w

    def _round_down_current(self, current: float) -> float:
        if current <= 0:
            return 0.0
        step = self.config.current_step
        rounded = math.floor(current / step) * step
        return round(rounded, 3)

    def _watts_per_amp(self) -> float:
        return self.config.voltage * self.config.phases

    def _reset_timers(self) -> None:
        self._surplus_started_at = None
        self._deficit_started_at = None


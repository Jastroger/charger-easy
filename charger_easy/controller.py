from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterable

from charger_easy.hardware import HardwareIO, HardwarePins, RaspberryPiHardware

CP_STATE_MAP = ("A", "E", "B", "C")
SUPPORTED_CURRENTS = (6, 8, 10, 13, 16, 20, 25, 32)
POT_VALUES = (45, 61, 74, 88, 103, 119, 136, 152, 167)
RLC_PIN_MAPPING = {"rlc1": 21, "rlc2": 20, "rlc3": 16, "rlc4": 5}


def amp_to_pot_value(amp: float) -> int:
    if amp <= 0:
        return POT_VALUES[0]

    for supported_amp, pot_value in zip(SUPPORTED_CURRENTS, POT_VALUES[1:]):
        if amp <= supported_amp:
            return pot_value
    return POT_VALUES[-1]


class ChargeController:
    CP_STATE_MAP = CP_STATE_MAP
    SUPPORTED_CURRENTS = SUPPORTED_CURRENTS
    POT_VALUES = POT_VALUES
    RLC_PIN_MAPPING = RLC_PIN_MAPPING

    def __init__(
        self,
        spi_bus: int = 0,
        spi_device: int = 0,
        spi_max_speed_hz: int = 976000,
        rlc_percentages_from_config: dict[str, float] | None = None,
        buzzer_config: dict[str, Any] | None = None,
        led_enabled: bool = False,
        hardware: HardwareIO | None = None,
        pins: HardwarePins | None = None,
        startup_delay_seconds: float = 13.1,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.pins = pins or HardwarePins()
        self.cp_pin_a = self.pins.cp_a
        self.cp_pin_b = self.pins.cp_b
        self.max_amp_pins = list(self.pins.max_amp)
        self.free_charge_pin = self.pins.free_charge_dip
        self.rlc_dip_pin = self.pins.rlc_dip
        self.led_green_pin = self.pins.led_green
        self.led_blue_pin = self.pins.led_blue
        self.buzzer_pin = self.pins.buzzer
        self.hardware = hardware or RaspberryPiHardware(spi_bus, spi_device, spi_max_speed_hz)
        self.led_enabled = led_enabled
        self.sleep = sleep
        self.startup_delay_seconds = startup_delay_seconds

        self.last_set_current = -1.0
        self.rlc_pins = self._build_rlc_mapping(rlc_percentages_from_config or {})

        self._setup_gpio(self.rlc_pins.values())
        self._setup_buzzer(buzzer_config or {})

        self.startup_initialize()
        if self.buzzer_enabled:
            self.play_melody("startup")

    def _build_rlc_mapping(self, rlc_percentages: dict[str, float]) -> dict[float, int]:
        mappings: list[dict[str, float | int]] = []
        for key, percentage in rlc_percentages.items():
            bcm_pin = RLC_PIN_MAPPING.get(key)
            if bcm_pin is None:
                self.logger.warning("RLC-Schluessel '%s' hat keine BCM-Pin-Zuordnung.", key)
                continue
            mappings.append({"percentage": float(percentage), "bcm_pin": bcm_pin})

        mappings.sort(key=lambda item: item["percentage"])
        return {float(item["percentage"]): int(item["bcm_pin"]) for item in mappings}

    def _setup_gpio(self, rlc_bcm_pins: Iterable[int]) -> None:
        self.hardware.setup_input([self.pins.cp_a, self.pins.cp_b], pull="down")
        self.hardware.setup_input(list(self.pins.max_amp), pull="up")
        self.hardware.setup_input(self.pins.free_charge_dip, pull="up")
        self.hardware.setup_input(self.pins.rlc_dip, pull="up")
        self.hardware.setup_output([self.pins.led_green, self.pins.led_blue])

        rlc_pin_list = list(rlc_bcm_pins)
        if rlc_pin_list:
            self.hardware.setup_input(rlc_pin_list, pull="down")

    def _setup_buzzer(self, buzzer_config: dict[str, Any]) -> None:
        self.hardware.setup_output(self.pins.buzzer)
        self.hardware.output(self.pins.buzzer, self.hardware.LOW)
        self.buzzer_pwm = self.hardware.create_pwm(self.pins.buzzer, 1000)
        self.buzzer_pwm.stop()

        self.buzzer_enabled = bool(buzzer_config.get("enabled", False))
        self.melodies = buzzer_config.get("melodies", {})

    def led(self) -> None:
        if not self.led_enabled:
            return

        self.hardware.output(
            self.pins.led_green,
            self.hardware.HIGH if self.is_evcc_mode_enabled() else self.hardware.LOW,
        )
        self.hardware.output(
            self.pins.led_blue,
            self.hardware.HIGH if self.is_rlc_enabled() else self.hardware.LOW,
        )

    def _write_pot(self, value: int, non_volatile: bool = False) -> None:
        msb = 0x20 if non_volatile else 0x00
        lsb = 0xFF - int(value)
        try:
            self.hardware.write_spi([msb, lsb])
        except Exception:
            self.logger.exception("Fehler beim Schreiben auf SPI")

    def startup_initialize(self) -> None:
        max_hw_current = self.get_max_hardware_current()
        self._write_pot(amp_to_pot_value(max_hw_current), non_volatile=True)
        if self.startup_delay_seconds > 0:
            self.sleep(self.startup_delay_seconds)

        self._write_pot(amp_to_pot_value(0), non_volatile=False)
        self.last_set_current = 0
        self.logger.info("Initialisierung abgeschlossen. HW-Limit: %sA. Aktiver Strom: 0A.", max_hw_current)

    def play_melody(
        self,
        melody_name: str,
        default_frequency: int = 1000,
        default_duration_ms: int = 200,
        duty_cycle: int = 80,
    ) -> None:
        if not self.buzzer_enabled:
            return

        melody_data = self.melodies.get(melody_name)
        if not melody_data or not melody_data.get("sequence"):
            self.logger.warning("Melodie '%s' nicht gefunden. Standard-Piepton wird abgespielt.", melody_name)
            self._beep(default_frequency, default_duration_ms, duty_cycle)
            return

        for note in melody_data["sequence"]:
            frequency = int(note.get("f", 0))
            duration_ms = int(note.get("d", 0))
            if frequency > 0 and duration_ms > 0:
                self._beep(frequency, duration_ms, duty_cycle)
            elif duration_ms > 0:
                self.sleep(duration_ms / 1000.0)

    def _beep(self, frequency: int, duration_ms: int, duty_cycle: int) -> None:
        try:
            self.buzzer_pwm.ChangeFrequency(frequency)
            self.buzzer_pwm.start(duty_cycle)
            self.sleep(duration_ms / 1000.0)
        except Exception:
            self.logger.exception("Fehler beim Buzzer")
        finally:
            self.buzzer_pwm.stop()

    def get_max_hardware_current(self) -> int:
        try:
            raw_values = [int(self.hardware.input(pin)) for pin in self.pins.max_amp[:3]]
            position = raw_values[0] + (raw_values[1] << 1) + (raw_values[2] << 2)
            if 0 <= position < len(SUPPORTED_CURRENTS):
                return SUPPORTED_CURRENTS[position]
            self.logger.warning("Ungueltige Schalterposition %s mit Inputs %s", position, raw_values)
            return SUPPORTED_CURRENTS[0]
        except Exception:
            self.logger.exception("Fehler beim Lesen des Drehschalters")
            return SUPPORTED_CURRENTS[0]

    def is_free_charging_enabled(self) -> bool:
        return self.hardware.input(self.pins.free_charge_dip) == self.hardware.LOW

    def is_evcc_mode_enabled(self) -> bool:
        return not self.is_free_charging_enabled()

    def is_rlc_enabled(self) -> bool:
        return self.hardware.input(self.pins.rlc_dip) == self.hardware.LOW

    def get_rlc_percentage(self) -> float:
        if not self.is_rlc_enabled():
            return 100.0

        for percentage, pin in self.rlc_pins.items():
            if self.hardware.input(pin) == self.hardware.HIGH:
                return percentage
        return 100.0

    def set_charge_current(self, requested_amperes: float, force: bool = False) -> float:
        requested_amperes = self._coerce_requested_current(requested_amperes)
        max_hw_current = max(0.0, float(self.get_max_hardware_current()))
        rlc_percentage = min(100.0, max(0.0, float(self.get_rlc_percentage())))
        rlc_limited_current = max_hw_current * (rlc_percentage / 100.0)
        effective_amperes = min(requested_amperes, rlc_limited_current)

        if force or effective_amperes != self.last_set_current:
            self.last_set_current = effective_amperes
            self._write_pot(amp_to_pot_value(effective_amperes), non_volatile=False)
        return effective_amperes

    def get_cp_state(self) -> str:
        pin_a = int(self.hardware.input(self.pins.cp_a))
        pin_b = int(self.hardware.input(self.pins.cp_b))
        index = (pin_a << 1) | pin_b
        return CP_STATE_MAP[index] if 0 <= index < len(CP_STATE_MAP) else "F"

    def cleanup(self) -> None:
        self.logger.info("Raeume GPIO und SPI auf...")
        try:
            self.set_charge_current(0, force=True)
        finally:
            self.buzzer_pwm.stop()
            self.hardware.close()

    @staticmethod
    def _coerce_requested_current(requested_amperes: float) -> float:
        try:
            return max(0.0, float(requested_amperes))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _amp_to_pot_value(amp: float) -> int:
        return amp_to_pot_value(amp)


JuiceBoosterControl = ChargeController

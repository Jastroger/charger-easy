import logging
import time
from typing import Dict, Iterable, List

import RPi.GPIO as GPIO
import spidev


class JuiceBoosterControl:
    CP_STATE_MAP = ["A", "E", "B", "C"]
    SUPPORTED_CURRENTS = [6, 8, 10, 13, 16, 20, 25, 32]
    POT_VALUES = [45, 61, 74, 88, 103, 119, 136, 152, 167]
    RLC_PIN_MAPPING = {"rlc1": 21, "rlc2": 20, "rlc3": 16, "rlc4": 5}

    def __init__(
        self,
        spi_bus: int = 0,
        spi_device: int = 0,
        spi_max_speed_hz: int = 976000,
        rlc_percentages_from_config: Dict[str, int] | None = None,
        buzzer_config: Dict | None = None,
        led_enabled: bool = False,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self._setup_pins()
        self.led_enabled = led_enabled

        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = spi_max_speed_hz

        self.last_set_current = -1.0
        self.rlc_pins = self._build_rlc_mapping(rlc_percentages_from_config or {})

        self._setup_gpio(self.rlc_pins.values())
        self._setup_buzzer(buzzer_config or {})

        self.startup_initialize()
        if self.buzzer_enabled:
            self.play_melody("startup")

    def _setup_pins(self) -> None:
        self.cp_pin_a = 6
        self.cp_pin_b = 26
        self.max_amp_pins = [18, 24, 23, 25]
        self.free_charge_pin = 22
        self.rlc_dip_pin = 27
        self.led_green_pin = 12
        self.led_blue_pin = 19
        self.buzzer_pin = 13

    def _build_rlc_mapping(self, rlc_percentages: Dict[str, int]) -> Dict[int, int]:
        mappings: List[dict] = []
        for key, percentage in rlc_percentages.items():
            bcm_pin = self.RLC_PIN_MAPPING.get(key)
            if bcm_pin is None:
                self.logger.warning("RLC-Schluessel '%s' hat keine BCM-Pin-Zuordnung.", key)
                continue
            mappings.append({"percentage": percentage, "bcm_pin": bcm_pin})

        mappings.sort(key=lambda item: item["percentage"])
        return {item["percentage"]: item["bcm_pin"] for item in mappings}

    def _setup_gpio(self, rlc_bcm_pins: Iterable[int]) -> None:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup([self.cp_pin_a, self.cp_pin_b], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(self.max_amp_pins, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.free_charge_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.rlc_dip_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.led_green_pin, GPIO.OUT)
        GPIO.setup(self.led_blue_pin, GPIO.OUT)

        rlc_pin_list = list(rlc_bcm_pins)
        if rlc_pin_list:
            GPIO.setup(rlc_pin_list, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def _setup_buzzer(self, buzzer_config: Dict) -> None:
        GPIO.setup(self.buzzer_pin, GPIO.OUT)
        GPIO.output(self.buzzer_pin, GPIO.LOW)
        self.buzzer_pwm = GPIO.PWM(self.buzzer_pin, 1000)
        self.buzzer_pwm.stop()

        self.buzzer_enabled = buzzer_config.get("enabled", False)
        self.melodies = buzzer_config.get("melodies", {})

    def led(self) -> None:
        if not self.led_enabled:
            return
        evcc_state = GPIO.input(self.free_charge_pin)
        rlc_state = GPIO.input(self.rlc_dip_pin)
        GPIO.output(self.led_green_pin, GPIO.HIGH if evcc_state == GPIO.HIGH else GPIO.LOW)
        GPIO.output(self.led_blue_pin, GPIO.HIGH if rlc_state == GPIO.LOW else GPIO.LOW)

    def _write_pot(self, value: int, non_volatile: bool = False) -> None:
        msb = 0x20 if non_volatile else 0x00
        lsb = 0xFF - int(value)
        try:
            self.spi.xfer2([msb, lsb])
        except Exception:
            self.logger.exception("Fehler beim Schreiben auf SPI")

    def _amp_to_pot_value(self, amp: float) -> int:
        if amp <= 0:
            return self.POT_VALUES[0]

        for supported_amp, pot_value in zip(self.SUPPORTED_CURRENTS, self.POT_VALUES[1:]):
            if amp <= supported_amp:
                return pot_value
        return self.POT_VALUES[-1]

    def startup_initialize(self) -> None:
        max_hw_current = self.get_max_hardware_current()
        self._write_pot(self._amp_to_pot_value(max_hw_current), non_volatile=True)
        time.sleep(13.1)

        self._write_pot(self._amp_to_pot_value(0), non_volatile=False)
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
            frequency = note.get("f", 0)
            duration_ms = note.get("d", 0)
            if frequency > 0 and duration_ms > 0:
                self._beep(frequency, duration_ms, duty_cycle)
            elif duration_ms > 0:
                time.sleep(duration_ms / 1000.0)

    def _beep(self, frequency: int, duration_ms: int, duty_cycle: int) -> None:
        try:
            self.buzzer_pwm.ChangeFrequency(frequency)
            self.buzzer_pwm.start(duty_cycle)
            time.sleep(duration_ms / 1000.0)
        except Exception:
            self.logger.exception("Fehler beim Buzzer")
        finally:
            self.buzzer_pwm.stop()

    def get_max_hardware_current(self) -> int:
        try:
            raw_values = [GPIO.input(pin) for pin in self.max_amp_pins[:3]]
            position = raw_values[0] + (raw_values[1] << 1) + (raw_values[2] << 2)
            if 0 <= position < len(self.SUPPORTED_CURRENTS):
                return self.SUPPORTED_CURRENTS[position]
            self.logger.warning("Ungueltige Schalterposition %s mit Inputs %s", position, raw_values)
            return self.SUPPORTED_CURRENTS[0]
        except Exception:
            self.logger.exception("Fehler beim Lesen des Drehschalters")
            return self.SUPPORTED_CURRENTS[0]

    def get_rlc_percentage(self) -> int:
        if not GPIO.input(self.rlc_dip_pin):
            return 100

        for percentage, pin in self.rlc_pins.items():
            if not GPIO.input(pin):
                return percentage
        return 100

    def is_free_charging_enabled(self) -> bool:
        return bool(GPIO.input(self.free_charge_pin))

    def set_charge_current(self, requested_amperes: float) -> float:
        max_hw_current = self.get_max_hardware_current()
        rlc_percentage = self.get_rlc_percentage()
        rlc_limited_current = max_hw_current * (rlc_percentage / 100.0)

        requested_amperes = max(0.0, float(requested_amperes))
        effective_amperes = min(requested_amperes, rlc_limited_current)

        if effective_amperes != self.last_set_current:
            self.last_set_current = effective_amperes
            self._write_pot(self._amp_to_pot_value(effective_amperes), non_volatile=False)
        return effective_amperes

    def get_cp_state(self) -> str:
        pin_a = GPIO.input(self.cp_pin_a)
        pin_b = GPIO.input(self.cp_pin_b)
        index = (pin_a << 1) | pin_b
        return self.CP_STATE_MAP[index] if 0 <= index < len(self.CP_STATE_MAP) else "F"

    def cleanup(self) -> None:
        self.logger.info("Raeume GPIO und SPI auf...")
        self.set_charge_current(0)
        self.spi.close()
        self.buzzer_pwm.stop()
        GPIO.cleanup()

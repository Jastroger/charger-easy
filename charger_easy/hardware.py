from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence


@dataclass(frozen=True)
class HardwarePins:
    cp_a: int = 6
    cp_b: int = 26
    max_amp: tuple[int, int, int, int] = (18, 24, 23, 25)
    free_charge_dip: int = 22
    rlc_dip: int = 27
    led_green: int = 12
    led_blue: int = 19
    buzzer: int = 13


class PwmOutput(Protocol):
    def ChangeFrequency(self, frequency: int) -> None: ...

    def start(self, duty_cycle: int) -> None: ...

    def stop(self) -> None: ...


class HardwareIO(Protocol):
    HIGH: int
    LOW: int

    def setup_input(self, pins: int | Sequence[int], pull: str) -> None: ...

    def setup_output(self, pins: int | Sequence[int]) -> None: ...

    def input(self, pin: int) -> int: ...

    def output(self, pin: int, value: int) -> None: ...

    def create_pwm(self, pin: int, frequency: int) -> PwmOutput: ...

    def write_spi(self, command: Iterable[int]) -> None: ...

    def close(self) -> None: ...


class RaspberryPiHardware:
    """Hardware adapter that keeps Raspberry Pi imports out of business logic."""

    def __init__(self, spi_bus: int = 0, spi_device: int = 0, spi_max_speed_hz: int = 976000) -> None:
        try:
            import RPi.GPIO as GPIO
            import spidev
        except ImportError as error:
            raise RuntimeError(
                "Raspberry-Pi-Hardwaremodule fehlen. Installiere RPi.GPIO und spidev auf dem Zielsystem."
            ) from error

        self.GPIO = GPIO
        self.HIGH = GPIO.HIGH
        self.LOW = GPIO.LOW

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = spi_max_speed_hz

    def setup_input(self, pins: int | Sequence[int], pull: str) -> None:
        pull_map = {
            "up": self.GPIO.PUD_UP,
            "down": self.GPIO.PUD_DOWN,
        }
        self.GPIO.setup(pins, self.GPIO.IN, pull_up_down=pull_map[pull])

    def setup_output(self, pins: int | Sequence[int]) -> None:
        self.GPIO.setup(pins, self.GPIO.OUT)

    def input(self, pin: int) -> int:
        return self.GPIO.input(pin)

    def output(self, pin: int, value: int) -> None:
        self.GPIO.output(pin, value)

    def create_pwm(self, pin: int, frequency: int) -> PwmOutput:
        return self.GPIO.PWM(pin, frequency)

    def write_spi(self, command: Iterable[int]) -> None:
        self.spi.xfer2(list(command))

    def close(self) -> None:
        self.spi.close()
        self.GPIO.cleanup()


from __future__ import annotations

from typing import Sequence


class FakePwm:
    def __init__(self, pin: int, frequency: int) -> None:
        self.pin = pin
        self.frequency = frequency
        self.started_with: list[int] = []
        self.stopped = False

    def ChangeFrequency(self, frequency: int) -> None:
        self.frequency = frequency

    def start(self, duty_cycle: int) -> None:
        self.started_with.append(duty_cycle)
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class FakeHardware:
    HIGH = 1
    LOW = 0

    def __init__(self) -> None:
        self.inputs: dict[int, int] = {}
        self.outputs: dict[int, int] = {}
        self.spi_writes: list[list[int]] = []
        self.pwms: list[FakePwm] = []
        self.closed = False

    def setup_input(self, pins: int | Sequence[int], pull: str) -> None:
        default_value = self.HIGH if pull == "up" else self.LOW
        for pin in self._pins(pins):
            self.inputs.setdefault(pin, default_value)

    def setup_output(self, pins: int | Sequence[int]) -> None:
        for pin in self._pins(pins):
            self.outputs.setdefault(pin, self.LOW)

    def input(self, pin: int) -> int:
        return self.inputs.get(pin, self.LOW)

    def output(self, pin: int, value: int) -> None:
        self.outputs[pin] = value

    def create_pwm(self, pin: int, frequency: int) -> FakePwm:
        pwm = FakePwm(pin, frequency)
        self.pwms.append(pwm)
        return pwm

    def write_spi(self, command) -> None:
        self.spi_writes.append(list(command))

    def close(self) -> None:
        self.closed = True

    def set_input(self, pin: int, value: int) -> None:
        self.inputs[pin] = value

    @staticmethod
    def _pins(pins: int | Sequence[int]) -> list[int]:
        if isinstance(pins, int):
            return [pins]
        return list(pins)


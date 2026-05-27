from __future__ import annotations

import unittest

from charger_easy.controller import ChargeController, RLC_PIN_MAPPING, amp_to_pot_value
from charger_easy.hardware import HardwarePins
from tests.fakes import FakeHardware


RLC_PERCENTAGES = {"rlc1": 75, "rlc2": 50, "rlc3": 25, "rlc4": 0}


class ControllerTests(unittest.TestCase):
    def build_controller(self, hardware: FakeHardware | None = None, led_enabled: bool = False) -> ChargeController:
        return ChargeController(
            rlc_percentages_from_config=RLC_PERCENTAGES,
            buzzer_config={"enabled": False, "melodies": {}},
            led_enabled=led_enabled,
            hardware=hardware or FakeHardware(),
            startup_delay_seconds=0,
            sleep=lambda _: None,
        )

    def test_amp_to_pot_value_mapping(self) -> None:
        self.assertEqual(amp_to_pot_value(0), 45)
        self.assertEqual(amp_to_pot_value(0.1), 61)
        self.assertEqual(amp_to_pot_value(6), 61)
        self.assertEqual(amp_to_pot_value(7.5), 74)
        self.assertEqual(amp_to_pot_value(32), 167)
        self.assertEqual(amp_to_pot_value(40), 167)

    def test_dip_switches_are_active_low_and_leds_match_mode(self) -> None:
        hardware = FakeHardware()
        controller = self.build_controller(hardware, led_enabled=True)
        pins = controller.pins

        self.assertFalse(controller.is_free_charging_enabled())
        self.assertTrue(controller.is_evcc_mode_enabled())
        self.assertFalse(controller.is_rlc_enabled())

        controller.led()
        self.assertEqual(hardware.outputs[pins.led_green], hardware.HIGH)
        self.assertEqual(hardware.outputs[pins.led_blue], hardware.LOW)

        hardware.set_input(pins.free_charge_dip, hardware.LOW)
        hardware.set_input(pins.rlc_dip, hardware.LOW)

        self.assertTrue(controller.is_free_charging_enabled())
        self.assertFalse(controller.is_evcc_mode_enabled())
        self.assertTrue(controller.is_rlc_enabled())

        controller.led()
        self.assertEqual(hardware.outputs[pins.led_green], hardware.LOW)
        self.assertEqual(hardware.outputs[pins.led_blue], hardware.HIGH)

    def test_rlc_uses_strongest_active_reduction(self) -> None:
        hardware = FakeHardware()
        controller = self.build_controller(hardware)

        hardware.set_input(controller.pins.rlc_dip, hardware.LOW)

        self.assertEqual(controller.get_rlc_percentage(), 100.0)

        hardware.set_input(RLC_PIN_MAPPING["rlc1"], hardware.HIGH)
        hardware.set_input(RLC_PIN_MAPPING["rlc3"], hardware.HIGH)
        self.assertEqual(controller.get_rlc_percentage(), 25.0)

        hardware.set_input(RLC_PIN_MAPPING["rlc4"], hardware.HIGH)
        self.assertEqual(controller.get_rlc_percentage(), 0.0)

    def test_set_current_limits_by_hardware_and_rlc(self) -> None:
        hardware = FakeHardware()
        pins = HardwarePins()
        hardware.set_input(pins.max_amp[0], hardware.LOW)
        hardware.set_input(pins.max_amp[1], hardware.LOW)
        hardware.set_input(pins.max_amp[2], hardware.HIGH)
        hardware.set_input(pins.rlc_dip, hardware.LOW)
        hardware.set_input(RLC_PIN_MAPPING["rlc2"], hardware.HIGH)

        controller = self.build_controller(hardware)
        hardware.spi_writes.clear()

        effective = controller.set_charge_current(20.0)

        self.assertEqual(effective, 8.0)
        self.assertEqual(hardware.spi_writes[-1], [0x00, 0xFF - amp_to_pot_value(8.0)])

        effective = controller.set_charge_current(-5)
        self.assertEqual(effective, 0.0)
        self.assertEqual(hardware.spi_writes[-1], [0x00, 0xFF - amp_to_pot_value(0)])

    def test_cp_state_mapping(self) -> None:
        hardware = FakeHardware()
        controller = self.build_controller(hardware)
        pins = controller.pins

        hardware.set_input(pins.cp_a, hardware.LOW)
        hardware.set_input(pins.cp_b, hardware.LOW)
        self.assertEqual(controller.get_cp_state(), "A")

        hardware.set_input(pins.cp_a, hardware.LOW)
        hardware.set_input(pins.cp_b, hardware.HIGH)
        self.assertEqual(controller.get_cp_state(), "E")

        hardware.set_input(pins.cp_a, hardware.HIGH)
        hardware.set_input(pins.cp_b, hardware.LOW)
        self.assertEqual(controller.get_cp_state(), "B")

        hardware.set_input(pins.cp_a, hardware.HIGH)
        hardware.set_input(pins.cp_b, hardware.HIGH)
        self.assertEqual(controller.get_cp_state(), "C")

    def test_cleanup_forces_zero_write_and_closes_hardware(self) -> None:
        hardware = FakeHardware()
        controller = self.build_controller(hardware)
        hardware.spi_writes.clear()

        controller.cleanup()

        self.assertEqual(hardware.spi_writes[-1], [0x00, 0xFF - amp_to_pot_value(0)])
        self.assertTrue(hardware.closed)
        self.assertTrue(hardware.pwms[-1].stopped)


if __name__ == "__main__":
    unittest.main()

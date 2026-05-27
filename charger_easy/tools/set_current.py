from __future__ import annotations

import argparse
from typing import Sequence

from charger_easy.controller import amp_to_pot_value
from charger_easy.hardware import RaspberryPiHardware


def set_pot_current(hardware: RaspberryPiHardware, amp_value: float, non_volatile: bool = False) -> int:
    raw_pot_value = amp_to_pot_value(amp_value)
    msb = 0x20 if non_volatile else 0x00
    lsb = 0xFF - int(raw_pot_value)
    hardware.write_spi([msb, lsb])
    return raw_pot_value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Set MCP4161 current limit for manual hardware tests")
    parser.add_argument("current", nargs="?", type=float, help="Current in ampere, 0..32. Omit for interactive mode.")
    parser.add_argument("--bus", type=int, default=0, help="SPI bus")
    parser.add_argument("--device", type=int, default=0, help="SPI device")
    parser.add_argument("--speed", type=int, default=976000, help="SPI max speed in Hz")
    parser.add_argument("--eeprom", action="store_true", help="Write non-volatile EEPROM register instead of RAM")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    hardware = RaspberryPiHardware(spi_bus=args.bus, spi_device=args.device, spi_max_speed_hz=args.speed)
    try:
        if args.current is not None:
            _validate_current(args.current)
            raw_value = set_pot_current(hardware, args.current, non_volatile=args.eeprom)
            print(f"Befehl gesendet: Ampere={args.current}A, Rohwert={raw_value}")
            return 0

        print("SPI-Schnittstelle erfolgreich geoeffnet.")
        print("--- Manueller Potentiometer-Test ---")
        print("Geben Sie den gewuenschten Ladestrom in Ampere ein (0..32).")
        print("Druecken Sie STRG+C zum Beenden.")
        while True:
            try:
                target_amp = float(input("\nNeuer Ladestrom (A): "))
                _validate_current(target_amp)
                raw_value = set_pot_current(hardware, target_amp, non_volatile=args.eeprom)
                print(f"Befehl gesendet: Ampere={target_amp}A, Rohwert={raw_value}")
            except ValueError as error:
                print(error)
    except KeyboardInterrupt:
        print("\nProgramm wird beendet. Setze Strom sicherheitshalber auf 0A.")
        set_pot_current(hardware, 0)
        return 0
    finally:
        hardware.close()
        print("SPI-Schnittstelle geschlossen.")


def _validate_current(current: float) -> None:
    if not 0 <= current <= 32:
        raise ValueError("Ungueltiger Wert. Bitte zwischen 0 und 32 eingeben.")


if __name__ == "__main__":
    raise SystemExit(main())


from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any, Sequence

from charger_easy.web import WebConfig, WebDashboardServer


class ConsoleLogger:
    def info(self, *args: Any) -> None:
        print(_format_log_message(*args))

    def debug(self, *args: Any) -> None:
        pass

    def exception(self, *args: Any) -> None:
        print(_format_log_message(*args))


def _format_log_message(*args: Any) -> str:
    if not args:
        return ""
    message = str(args[0])
    if len(args) == 1:
        return message
    try:
        return message % args[1:]
    except (TypeError, ValueError):
        return " ".join(str(arg) for arg in args)


class FakeRuntime:
    def __init__(self, mode: str = "pv", current: float = 10.0) -> None:
        self.mode = mode
        self.current = current

    def get_web_state(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "effective_mode": self.mode,
            "cp_state": "C",
            "vehicle_connected": True,
            "is_charging": self.mode != "off" and self.current > 0,
            "hardware_override_free_charge": False,
            "grid_power_w": -1850,
            "pv_surplus_w": 1750,
            "target_current_A": 8,
            "effective_current_A": self.current if self.mode != "off" else 0,
            "instant_current_A": self.current,
            "hw_max_current": 16,
            "rlc_percentage": 100,
            "limit_reason": "off" if self.mode == "off" else "pv_surplus_available",
            "pv_input_stale": False,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }

    def set_mode(self, mode: str, source: str = "web") -> bool:
        if mode not in {"off", "pv", "instant"}:
            return False
        self.mode = mode
        return True

    def set_instant_current(self, current: Any, source: str = "web") -> bool:
        try:
            self.current = max(0.0, min(32.0, float(current)))
        except (TypeError, ValueError):
            return False
        return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the web dashboard with fake runtime data")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the local web server")
    parser.add_argument("--port", type=int, default=8080, help="Port for the local web server")
    parser.add_argument("--mode", choices=("off", "pv", "instant"), default="pv", help="Initial charger mode")
    parser.add_argument("--current", type=float, default=10.0, help="Initial current in ampere")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = WebDashboardServer(
        FakeRuntime(mode=args.mode, current=args.current),
        WebConfig(host=args.host, port=args.port),
        ConsoleLogger(),
    )
    server.start()
    print(f"Open: {server.url}")
    try:
        input("Enter zum Beenden...")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

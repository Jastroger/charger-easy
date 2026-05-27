from __future__ import annotations

import argparse
import sys
from typing import Sequence

from charger_easy.config import ConfigError, load_config, resolve_config_path
from charger_easy.logging_config import configure_logger
from charger_easy.runtime import ChargerRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Juice CHARGER Easy MQTT control service")
    parser.add_argument(
        "--config",
        help="Pfad zur config.yaml. Standard: CHARGER_EASY_CONFIG oder /opt/juice-charger/config.yaml",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = resolve_config_path(args.config)

    try:
        config = load_config(config_path)
        logger = configure_logger(config)
    except ConfigError as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 1

    runtime = ChargerRuntime(config=config, logger=logger)
    runtime.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


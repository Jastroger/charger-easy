from charger_easy.cli import main
from charger_easy.config import DEFAULT_CONFIG_PATH as CONFIG_PATH
from charger_easy.config import ConfigError, load_config, resolve_config_path
from charger_easy.logging_config import configure_logger
from charger_easy.runtime import ChargerRuntime

__all__ = [
    "CONFIG_PATH",
    "ChargerRuntime",
    "ConfigError",
    "configure_logger",
    "load_config",
    "main",
    "resolve_config_path",
]


if __name__ == "__main__":
    raise SystemExit(main())

"""Application paths and optional user configuration.

Data lives in %LOCALAPPDATA%\\Sessionly by default. ``SESSIONLY_DATA_DIR`` (used by
tests) or ``data_dir`` in config.toml override it. Secrets never belong here.
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from sessionly import APP_NAME

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "sessionly.db"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


def load_config() -> AppConfig:
    env_dir = os.environ.get("SESSIONLY_DATA_DIR")
    data_dir = Path(env_dir) if env_dir else default_data_dir()
    log_level = "INFO"

    config_file = data_dir / "config.toml"
    if config_file.exists():
        try:
            raw = tomllib.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            # Logging is not configured yet; fall back to defaults and say so later.
            logging.getLogger(__name__).warning("Ignoring unreadable config.toml: %s", exc)
            raw = {}
        if not env_dir and isinstance(raw.get("data_dir"), str):
            data_dir = Path(raw["data_dir"]).expanduser()
        level = str(raw.get("log_level", "INFO")).upper()
        if level in _VALID_LOG_LEVELS:
            log_level = level

    data_dir.mkdir(parents=True, exist_ok=True)
    return AppConfig(data_dir=data_dir, log_level=log_level)

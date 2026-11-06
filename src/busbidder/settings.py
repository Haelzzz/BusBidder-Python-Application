"""Application settings read from config/settings.json."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from busbidder.exceptions import ConfigError
from busbidder.paths import PROJECT_ROOT, SETTINGS_FILE


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated settings. Relative paths in the file are resolved from the project root."""

    origin: str
    companies_file: Path
    destinations_file: Path
    offers_file: Path
    review_file: Path  
    log_file: Path
    log_level: str
    rating_min: float
    rating_max: float


def load_settings(path: Path = SETTINGS_FILE) -> Settings:
    """Read and check the settings file, raising ``ConfigError`` if it is unusable."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"settings file not found: {path}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read settings file {path}: {exc}") from exc

    try:
        settings = Settings(
            origin=str(data["origin"]),
            companies_file=_resolve(data["data"]["companies"]),
            destinations_file=_resolve(data["data"]["destinations"]),
            offers_file=_resolve(data["data"]["offers"]),
            review_file=_resolve(data["validation"]["review_file"]),
            log_file=_resolve(data["logging"]["file"]),
            log_level=str(data["logging"]["level"]).upper(),
            rating_min=float(data["validation"]["rating_min"]),
            rating_max=float(data["validation"]["rating_max"]),
        )
    except KeyError as exc:
        raise ConfigError(f"{path}: missing setting {exc}") from None
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path}: invalid setting value ({exc})") from exc

    if settings.rating_min >= settings.rating_max:
        raise ConfigError(f"{path}: rating_min must be below rating_max")
    if settings.log_level not in logging.getLevelNamesMapping():
        raise ConfigError(f"{path}: unknown log level {settings.log_level!r}")
    return settings


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path

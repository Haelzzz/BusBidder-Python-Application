"""Reads traveller profiles from config/profiles/*.json.

A profile file looks like this::

    {
      "name": "Business traveller",
      "description": "Needs a direct, changeable trip leaving early.",
      "preferred_departure": "07:30",
      "requirements": {"max_transfers": 0, "require_changeable": true},
      "weights": {"price": 0.10, "duration": 0.40, "departure": 0.30, "flexibility": 0.20}
    }

Profiles are configuration, so any problem is a ``ConfigError`` naming the
file. Unknown keys are rejected rather than ignored, so a typo such as
"weight" cannot silently produce a different traveller.
"""

import json
import logging
from datetime import time
from pathlib import Path
from typing import Any

from busbidder.exceptions import ConfigError, InvalidWeightsError
from busbidder.models import TravellerProfile
from busbidder.paths import PROFILES_DIR
from busbidder.patterns import TIME_RE
from busbidder.ranking import validate_weights

logger = logging.getLogger(__name__)

PROFILE_KEYS = {"name", "description", "preferred_departure", "requirements", "weights"}
# Requirement -> (type, may be null)
REQUIREMENT_TYPES: dict[str, tuple[type, bool]] = {
    "max_transfers": (int, True),
    "min_luggage_kg": (int, False),
    "require_changeable": (bool, False),
    "require_refundable": (bool, False),
}


def load_profiles(directory: Path = PROFILES_DIR) -> dict[str, TravellerProfile]:
    """All profiles in ``directory``, keyed by file name without .json, in alphabetical order."""
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ConfigError(f"no traveller profiles found in {directory}")
    profiles = {path.stem: load_profile(path) for path in paths}
    logger.info("Loaded %d traveller profiles: %s", len(profiles), ", ".join(profiles))
    return profiles


def load_profile(path: Path) -> TravellerProfile:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ConfigError(f"profile not found: {path}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read profile {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"{path}: a profile must be a JSON object")
    unknown = sorted(set(data) - PROFILE_KEYS)
    if unknown:
        raise ConfigError(f"{path}: unknown keys {unknown} (allowed: {sorted(PROFILE_KEYS)})")

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{path}: 'name' must be non-empty text")
    description = data.get("description", "")
    if not isinstance(description, str):
        raise ConfigError(f"{path}: 'description' must be text")

    weights = data.get("weights")
    if not isinstance(weights, dict):
        raise ConfigError(f"{path}: 'weights' must be an object of criterion weights")
    try:
        weights = validate_weights(weights)
    except InvalidWeightsError as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    return TravellerProfile(
        key=path.stem,
        name=name.strip(),
        description=description.strip(),
        weights=weights,
        preferred_departure=_parse_time(path, data.get("preferred_departure")),
        **_parse_requirements(path, data.get("requirements", {})),
    )


def _parse_time(path: Path, value: Any) -> time | None:
    if value is None:
        return None
    match = TIME_RE.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ConfigError(f"{path}: 'preferred_departure' must be a time HH:MM, got {value!r}")
    return time(int(match["hour"]), int(match["minute"]))


def _parse_requirements(path: Path, requirements: Any) -> dict[str, Any]:
    if not isinstance(requirements, dict):
        raise ConfigError(f"{path}: 'requirements' must be an object")
    parsed: dict[str, Any] = {}
    for key, value in requirements.items():
        if key not in REQUIREMENT_TYPES:
            raise ConfigError(f"{path}: unknown requirement {key!r} (allowed: {sorted(REQUIREMENT_TYPES)})")
        expected, nullable = REQUIREMENT_TYPES[key]
        if value is None and nullable:
            parsed[key] = None
            continue
        # bool is a subclass of int in Python, so true must not count as a number.
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise ConfigError(f"{path}: requirement {key!r} must be {expected.__name__}, got {value!r}")
        if expected is int and value < 0:
            raise ConfigError(f"{path}: requirement {key!r} cannot be negative, got {value}")
        parsed[key] = value
    return parsed

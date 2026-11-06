"""Tests for reading config/settings.json."""

import json
from pathlib import Path

import pytest

from busbidder.exceptions import ConfigError
from busbidder.paths import PROJECT_ROOT
from busbidder.settings import load_settings

VALID = {
    "origin": "Madrid",
    "data": {"companies": "data/companies.json", "destinations": "data/destinations.json", "offers": "data/offers.csv"},
    "validation": {"rating_min": 1.0, "rating_max": 5.0, "review_file": "logs/rejected_records.csv"},
    "logging": {"file": "logs/busbidder.log", "level": "info"},
}


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_project_settings_file_is_valid() -> None:
    settings = load_settings()
    assert settings.offers_file == PROJECT_ROOT / "data" / "offers.csv"


def test_relative_paths_resolve_from_project_root(tmp_path: Path) -> None:
    settings = load_settings(write(tmp_path, VALID))
    assert settings.companies_file == PROJECT_ROOT / "data" / "companies.json"
    assert settings.log_level == "INFO"


def test_missing_settings_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "settings.json")


def test_missing_key(tmp_path: Path) -> None:
    data = {key: value for key, value in VALID.items() if key != "validation"}
    with pytest.raises(ConfigError, match="missing setting 'validation'"):
        load_settings(write(tmp_path, data))


@pytest.mark.parametrize("validation", [
    {"rating_min": 5.0, "rating_max": 5.0, "review_file": "x.csv"},
    {"rating_min": "low", "rating_max": 5.0, "review_file": "x.csv"},
])
def test_invalid_rating_scale(tmp_path: Path, validation: dict) -> None:
    with pytest.raises(ConfigError):
        load_settings(write(tmp_path, VALID | {"validation": validation}))


def test_unknown_log_level(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="log level"):
        load_settings(write(tmp_path, VALID | {"logging": {"file": "x.log", "level": "LOUD"}}))

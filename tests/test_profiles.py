"""Tests for traveller profiles: loading, validation, and different recommendations."""

import dataclasses
import json
from datetime import date, time
from pathlib import Path

import pytest

from busbidder.data_io.loader import load_marketplace
from busbidder.data_io.profiles import load_profile, load_profiles
from busbidder.exceptions import ConfigError
from busbidder.filtering import filter_offers
from busbidder.models import TravellerProfile, Trip
from busbidder.ranking import rank_offers
from busbidder.settings import load_settings

SPEC_TRIP = Trip("MAL", date(2026, 7, 12), date(2026, 7, 14), max_budget_eur=50.0)
VALID = {
    "name": "Test traveller",
    "description": "For tests.",
    "preferred_departure": "08:15",
    "requirements": {"max_transfers": 0, "min_luggage_kg": 20, "require_changeable": True},
    "weights": {"price": 0.4, "duration": 0.3, "departure": 0.2, "flexibility": 0.1},
}


def write(tmp_path: Path, data: object, name: str = "test.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- The project's profiles ------------------------------------------------

def test_project_profiles_load() -> None:
    profiles = load_profiles()
    assert list(profiles) == ["balanced", "budget", "business", "eco", "flexible_tourist"]


@pytest.mark.parametrize("key", ["balanced", "budget", "business", "eco", "flexible_tourist"])
def test_project_profiles_use_at_least_four_criteria(key: str) -> None:
    # The specification requires the ranking to use at least four criteria.
    weights = load_profiles()[key].weights
    assert sum(1 for weight in weights.values() if weight > 0) >= 4
    assert sum(weights.values()) == pytest.approx(1.0)


def test_same_offers_give_different_recommendations(tmp_path: Path) -> None:
    settings = dataclasses.replace(load_settings(), review_file=tmp_path / "rejected.csv")
    repository, _ = load_marketplace(settings)
    recommended = {}
    for key, profile in load_profiles().items():
        request = profile.request_for(SPEC_TRIP)
        accepted = filter_offers(repository.offers_to("MAL"), request).accepted
        recommended[key] = rank_offers(accepted, request).top.offer.offer_id
    assert len(set(recommended.values())) >= 3
    assert recommended["budget"] != recommended["flexible_tourist"] != recommended["eco"]


# --- Loading one profile -----------------------------------------------------

def test_valid_profile_is_converted(tmp_path: Path) -> None:
    profile = load_profile(write(tmp_path, VALID, "business_test.json"))
    assert profile == TravellerProfile(
        key="business_test",
        name="Test traveller",
        description="For tests.",
        weights=VALID["weights"],
        preferred_departure=time(8, 15),
        max_transfers=0,
        min_luggage_kg=20,
        require_changeable=True,
    )


def test_optional_parts_may_be_left_out(tmp_path: Path) -> None:
    profile = load_profile(write(tmp_path, {"name": "Minimal", "weights": {"price": 1.0}}))
    assert profile.preferred_departure is None
    assert profile.max_transfers is None and profile.min_luggage_kg == 0
    assert not profile.require_changeable and not profile.require_refundable


def test_request_combines_profile_and_trip(tmp_path: Path) -> None:
    profile = load_profile(write(tmp_path, VALID))
    trip = Trip("BCN", date(2026, 7, 9), date(2026, 7, 10), seats=2, max_budget_eur=120.0, max_duration_min=480)
    request = profile.request_for(trip)
    # From the trip:
    assert (request.destination_id, request.earliest_date, request.latest_date) == ("BCN", trip.earliest_date,
                                                                                    trip.latest_date)
    assert (request.seats, request.max_budget_eur, request.max_duration_min) == (2, 120.0, 480)
    # From the profile:
    assert request.preferred_departure == time(8, 15)
    assert (request.max_transfers, request.min_luggage_kg, request.require_changeable) == (0, 20, True)
    assert request.weights == VALID["weights"]
    assert request.traveller_name == "Test traveller"


@pytest.mark.parametrize("changes, message", [
    ({"weight": {"price": 1.0}}, "unknown keys"),  # typo
    ({"name": ""}, "'name' must be non-empty"),
    ({"name": None}, "'name' must be non-empty"),
    ({"description": 5}, "'description' must be text"),
    ({"weights": None}, "'weights' must be an object"),
    ({"weights": {"price": 0.5}}, "must total 1.0"),
    ({"weights": {"price": 0.5, "comfort": 0.5}}, "unknown criterion"),
    ({"preferred_departure": "25:00"}, "must be a time HH:MM"),
    ({"preferred_departure": 900}, "must be a time HH:MM"),
    ({"requirements": []}, "'requirements' must be an object"),
    ({"requirements": {"max_budget_eur": 50}}, "unknown requirement"),  # budget belongs to the trip
    ({"requirements": {"max_transfers": "1"}}, "must be int"),
    ({"requirements": {"max_transfers": True}}, "must be int"),
    ({"requirements": {"min_luggage_kg": -5}}, "cannot be negative"),
    ({"requirements": {"min_luggage_kg": None}}, "must be int"),
    ({"requirements": {"require_changeable": "yes"}}, "must be bool"),
], ids=str)
def test_invalid_profile_is_rejected(tmp_path: Path, changes: dict, message: str) -> None:
    data = VALID | changes
    if "weight" in changes:
        del data["weights"]
    with pytest.raises(ConfigError, match=message):
        load_profile(write(tmp_path, data))


def test_null_max_transfers_means_no_limit(tmp_path: Path) -> None:
    profile = load_profile(write(tmp_path, VALID | {"requirements": {"max_transfers": None}}))
    assert profile.max_transfers is None


@pytest.mark.parametrize("content, message", [
    ("{not json", "cannot read profile"),
    ("[1, 2]", "must be a JSON object"),
])
def test_unreadable_profile(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_profile(path)


def test_missing_profile_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_profile(tmp_path / "nope.json")


def test_directory_without_profiles(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no traveller profiles"):
        load_profiles(tmp_path)


def test_one_bad_profile_stops_loading(tmp_path: Path) -> None:
    write(tmp_path, VALID, "good.json")
    write(tmp_path, VALID | {"weights": {"price": 2.0}}, "bad.json")
    with pytest.raises(ConfigError, match="bad.json"):
        load_profiles(tmp_path)

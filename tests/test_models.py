"""Tests for the domain model."""

import dataclasses
from datetime import date, datetime

import pytest

from busbidder.exceptions import InvalidRequestError
from busbidder.models import Offer, TravellerRequest


def test_offer_derived_values(offer: Offer) -> None:
    assert offer.duration_min == 375
    assert offer.travel_date == date(2026, 7, 12)
    assert offer.is_direct
    assert not offer.is_overnight


def test_overnight_offer_has_positive_duration(offer: Offer) -> None:
    offer.departure = datetime(2026, 7, 12, 23, 30)
    offer.arrival = datetime(2026, 7, 13, 6, 0)
    assert offer.is_overnight
    assert offer.duration_min == 390


def test_fare_conditions_are_immutable(offer: Offer) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        offer.fare.changeable = False  # type: ignore[misc]


def test_request_window_is_inclusive() -> None:
    request = TravellerRequest("MAL", date(2026, 7, 12), date(2026, 7, 14))
    assert request.covers(date(2026, 7, 12))
    assert request.covers(date(2026, 7, 14))
    assert not request.covers(date(2026, 7, 15))


def test_request_single_day_window_is_allowed() -> None:
    TravellerRequest("MAL", date(2026, 7, 12), date(2026, 7, 12))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"latest_date": date(2026, 7, 11)},
        {"seats": 0},
        {"max_budget_eur": -1.0},
        {"max_transfers": -1},
        {"max_duration_min": 0},
        {"min_luggage_kg": -1},
    ],
)
def test_request_rejects_inconsistent_input(kwargs: dict) -> None:
    base = {"destination_id": "MAL", "earliest_date": date(2026, 7, 12), "latest_date": date(2026, 7, 14)}
    with pytest.raises(InvalidRequestError):
        TravellerRequest(**(base | kwargs))

"""Tests for the individual hard constraints, including their boundaries.

The ``offer`` fixture (conftest.py) is SolRuta to Malaga on 12 July 2026,
08:30-14:45 (6h15), EUR 32.50, direct, 12 seats, standard fare: changeable,
not refundable, 20 kg luggage.
"""

import dataclasses
from datetime import date, datetime

import pytest

from busbidder.filtering.base import CONSTRAINTS
from busbidder.filtering.engine import filter_offers  # noqa: F401  (importing registers the constraints)
from busbidder.models import FareConditions, FareType, Offer, TravellerRequest

ALWAYS_ACTIVE = ["destination", "travel_window", "seats"]
OPTIONAL = ["budget", "max_transfers", "max_duration", "luggage", "changeable", "refundable"]


def request(**changes) -> TravellerRequest:
    base = TravellerRequest("MAL", date(2026, 7, 12), date(2026, 7, 14))
    return dataclasses.replace(base, **changes)


def violation(name: str, offer: Offer, **changes) -> str | None:
    return CONSTRAINTS.create(name).violation(offer, request(**changes))


def test_all_constraints_are_registered_in_display_order() -> None:
    assert CONSTRAINTS.names() == ALWAYS_ACTIVE + OPTIONAL


@pytest.mark.parametrize("name", ALWAYS_ACTIVE)
def test_core_constraints_are_always_active(name: str) -> None:
    assert CONSTRAINTS.create(name).is_active(request())


@pytest.mark.parametrize("name", OPTIONAL)
def test_optional_constraints_are_inactive_by_default(name: str) -> None:
    assert not CONSTRAINTS.create(name).is_active(request())


@pytest.mark.parametrize("name, changes", [
    ("budget", {"max_budget_eur": 50.0}),
    ("budget", {"max_budget_eur": 0.0}),  # zero is a limit, not "no limit"
    ("max_transfers", {"max_transfers": 0}),
    ("max_duration", {"max_duration_min": 300}),
    ("luggage", {"min_luggage_kg": 10}),
    ("changeable", {"require_changeable": True}),
    ("refundable", {"require_refundable": True}),
], ids=str)
def test_optional_constraint_is_active_when_set(name: str, changes: dict) -> None:
    assert CONSTRAINTS.create(name).is_active(request(**changes))


# --- Pass / fail with boundaries ------------------------------------------

def test_destination(offer: Offer) -> None:
    assert violation("destination", offer) is None
    assert violation("destination", offer, destination_id="BCN") == "goes to Malaga"


@pytest.mark.parametrize("earliest, latest, ok", [
    (date(2026, 7, 12), date(2026, 7, 12), True),  # single-day window
    (date(2026, 7, 10), date(2026, 7, 12), True),  # departure on the last day
    (date(2026, 7, 12), date(2026, 7, 20), True),  # departure on the first day
    (date(2026, 7, 13), date(2026, 7, 14), False),  # one day too early
    (date(2026, 7, 10), date(2026, 7, 11), False),  # one day too late
])
def test_travel_window_is_inclusive(offer: Offer, earliest: date, latest: date, ok: bool) -> None:
    assert (violation("travel_window", offer, earliest_date=earliest, latest_date=latest) is None) == ok


def test_overnight_arrival_after_window_still_passes(offer: Offer) -> None:
    offer.departure = datetime(2026, 7, 14, 23, 30)
    offer.arrival = datetime(2026, 7, 15, 6, 0)
    assert violation("travel_window", offer) is None


@pytest.mark.parametrize("seats_needed, ok", [(1, True), (12, True), (13, False)])
def test_seats(offer: Offer, seats_needed: int, ok: bool) -> None:
    assert (violation("seats", offer, seats=seats_needed) is None) == ok


@pytest.mark.parametrize("budget, seats, ok", [
    (32.50, 1, True),  # exactly the price
    (32.49, 1, False),  # one cent short
    (65.00, 2, True),  # budget covers the whole booking
    (64.99, 2, False),
])
def test_budget_covers_all_seats(offer: Offer, budget: float, seats: int, ok: bool) -> None:
    assert (violation("budget", offer, max_budget_eur=budget, seats=seats) is None) == ok


@pytest.mark.parametrize("transfers, limit, ok", [(0, 0, True), (1, 1, True), (2, 1, False), (1, 0, False)])
def test_max_transfers(offer: Offer, transfers: int, limit: int, ok: bool) -> None:
    offer.transfers = transfers
    assert (violation("max_transfers", offer, max_transfers=limit) is None) == ok


@pytest.mark.parametrize("limit, ok", [(375, True), (374, False)])  # offer takes 375 minutes
def test_max_duration(offer: Offer, limit: int, ok: bool) -> None:
    assert (violation("max_duration", offer, max_duration_min=limit) is None) == ok


def test_max_duration_reason_is_readable(offer: Offer) -> None:
    assert violation("max_duration", offer, max_duration_min=300) == "takes 6h15"


@pytest.mark.parametrize("needed, ok", [(20, True), (21, False)])  # offer includes 20 kg
def test_luggage(offer: Offer, needed: int, ok: bool) -> None:
    assert (violation("luggage", offer, min_luggage_kg=needed) is None) == ok


@pytest.mark.parametrize("fare_type, changeable, refundable", [
    (FareType.BASIC, False, False),
    (FareType.STANDARD, True, False),
    (FareType.FLEX, True, True),
])
def test_flexibility_requirements(offer: Offer, fare_type: FareType, changeable: bool, refundable: bool) -> None:
    offer.fare = FareConditions(fare_type, changeable, refundable, 20)
    assert (violation("changeable", offer, require_changeable=True) is None) == changeable
    assert (violation("refundable", offer, require_refundable=True) is None) == refundable


def test_requirement_texts_describe_the_request() -> None:
    req = request(max_budget_eur=50, max_duration_min=390, seats=2)
    assert CONSTRAINTS.create("budget").requirement(req) == "total price at most EUR 50.00"
    assert CONSTRAINTS.create("max_duration").requirement(req) == "journey at most 6h30"
    assert CONSTRAINTS.create("seats").requirement(req) == "at least 2 seat(s) available"

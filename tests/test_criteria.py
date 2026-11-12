"""Tests for the individual criteria: raw values and scaling to 0-100."""

import dataclasses
from datetime import date, datetime, time

import pytest

from busbidder.models import FareConditions, FareType, Offer, TravellerRequest
from busbidder.ranking.base import CRITERIA
from busbidder.ranking.engine import rank_offers  # noqa: F401  (importing registers the criteria)

REQUEST = TravellerRequest("MAL", date(2026, 7, 12), date(2026, 7, 14), preferred_departure=time(9, 0))


def criterion(name: str):
    return CRITERIA.create(name)


def test_criteria_are_registered_in_column_order() -> None:
    assert CRITERIA.names() == ["price", "duration", "departure", "flexibility", "emissions"]


# --- Ratio to best (price, duration, emissions) ----------------------------

@pytest.mark.parametrize("raws, expected", [
    ([30.0, 60.0, 45.0], [100.0, 50.0, 66.667]),  # twice the best value scores half
    ([30.0, 30.5], [100.0, 98.361]),  # a small difference stays small
    ([42.0], [100.0]),  # a single offer is the best
    ([20.0, 20.0], [100.0, 100.0]),  # equal values, no division problems
    ([0.0, 5.0], [100.0, 0.0]),  # a best value of zero (e.g. zero emissions)
    ([None, 10.0, 20.0], [None, 100.0, 50.0]),  # missing stays missing
    ([None, None], [None, None]),
    ([], []),
], ids=str)
def test_ratio_to_best(raws: list, expected: list) -> None:
    scores = criterion("price").normalise(raws)
    assert scores == [None if e is None else pytest.approx(e, abs=0.001) for e in expected]


def test_one_extreme_offer_does_not_squash_the_others() -> None:
    # With min-max scaling the EUR 200 offer would push 30 and 35 to 100 and 97;
    # with ratio-to-best their scores do not depend on it at all.
    with_outlier = criterion("price").normalise([30.0, 35.0, 200.0])
    without = criterion("price").normalise([30.0, 35.0])
    assert with_outlier[:2] == without


def test_raw_values(offer: Offer) -> None:
    offer.co2_kg = 15.9
    assert criterion("price").raw_value(offer, REQUEST) == 32.5
    assert criterion("duration").raw_value(offer, REQUEST) == 375
    assert criterion("emissions").raw_value(offer, REQUEST) == 15.9
    offer.co2_kg = None
    assert criterion("emissions").raw_value(offer, REQUEST) is None


# --- Departure convenience -------------------------------------------------

@pytest.mark.parametrize("departs, preferred, minutes", [
    ("09:00", "09:00", 0),
    ("12:15", "09:00", 195),
    ("06:00", "09:00", 180),  # earlier counts the same as later
    ("23:00", "01:00", 120),  # around midnight: 2 hours, not 22
    ("01:00", "23:00", 120),
    ("21:00", "09:00", 720),  # the furthest possible
])
def test_departure_difference_is_measured_around_the_clock(
    offer: Offer, departs: str, preferred: str, minutes: int,
) -> None:
    hour, minute = map(int, departs.split(":"))
    offer.departure = datetime(2026, 7, 12, hour, minute)
    request = dataclasses.replace(REQUEST, preferred_departure=time.fromisoformat(preferred))
    assert criterion("departure").raw_value(offer, request) == minutes


@pytest.mark.parametrize("minutes, score", [(0, 100), (90, 75), (180, 50), (359, 0.278), (360, 0), (720, 0)])
def test_departure_score_falls_to_zero_at_six_hours(minutes: int, score: float) -> None:
    assert criterion("departure").score(minutes) == pytest.approx(score, abs=0.001)


def test_departure_without_preferred_time_is_missing(offer: Offer) -> None:
    request = dataclasses.replace(REQUEST, preferred_departure=None)
    assert criterion("departure").raw_value(offer, request) is None


# --- Flexibility (categorical) -----------------------------------------------

@pytest.mark.parametrize("fare, level, score, label", [
    (FareConditions(FareType.BASIC, False, False, 10), 0, 0, "none"),
    (FareConditions(FareType.STANDARD, True, False, 20), 1, 60, "change"),
    (FareConditions(FareType.FLEX, True, True, 30), 2, 100, "refund"),
])
def test_flexibility_levels(offer: Offer, fare: FareConditions, level: int, score: float, label: str) -> None:
    offer.fare = fare
    flexibility = criterion("flexibility")
    assert flexibility.raw_value(offer, REQUEST) == level
    assert flexibility.score(level) == score
    assert flexibility.format_raw(level) == label


# --- Display -----------------------------------------------------------------

@pytest.mark.parametrize("name, raw, text", [
    ("price", 31.5, "31.50"),
    ("duration", 405, "6h45"),
    ("departure", 0, "on time"),
    ("departure", 195, "3h15 off"),
    ("emissions", 15.94, "15.9"),
])
def test_raw_values_are_formatted_for_display(name: str, raw: float, text: str) -> None:
    assert criterion(name).format_raw(raw) == text

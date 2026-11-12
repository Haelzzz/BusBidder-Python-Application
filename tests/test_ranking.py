"""Tests for the ranking engine: weights, totals, ties, missing values, reproducibility."""

import dataclasses
import random
from datetime import date, datetime, time, timedelta

import pytest

from busbidder.data_io.loader import load_marketplace
from busbidder.exceptions import InvalidWeightsError
from busbidder.filtering import filter_offers
from busbidder.models import FareConditions, FareType, Offer, TravellerRequest
from busbidder.ranking import rank_offers, validate_weights
from busbidder.settings import load_settings

SPEC_WEIGHTS = {"price": 0.40, "duration": 0.25, "departure": 0.15, "flexibility": 0.20}
REQUEST = TravellerRequest("MAL", date(2026, 7, 12), date(2026, 7, 14),
                           preferred_departure=time(9, 0), weights=SPEC_WEIGHTS)

STANDARD = FareConditions(FareType.STANDARD, True, False, 20)
FLEX = FareConditions(FareType.FLEX, True, True, 30)


def make(offer: Offer, offer_id: str, price: float, departs: str, minutes: int, fare: FareConditions) -> Offer:
    """A copy of ``offer`` departing 12 July at ``departs`` and taking ``minutes``."""
    departure = datetime.combine(date(2026, 7, 12), time.fromisoformat(departs))
    return dataclasses.replace(offer, offer_id=offer_id, price_eur=price, departure=departure,
                               arrival=departure + timedelta(minutes=minutes), fare=fare)


@pytest.fixture
def worked_example(offer: Offer) -> list[Offer]:
    """The three offers from the design discussion (A, B, C)."""
    return [
        make(offer, "OF-SOL-MAL-0001", 30.00, "12:15", 7 * 60, STANDARD),  # A
        make(offer, "OF-SOL-MAL-0002", 45.00, "09:00", 6 * 60, FLEX),  # B
        make(offer, "OF-SOL-MAL-0003", 49.50, "15:00", 5 * 60 + 20, STANDARD),  # C
    ]


# --- Weights -----------------------------------------------------------------

def test_valid_weights_are_accepted() -> None:
    assert validate_weights(SPEC_WEIGHTS) == SPEC_WEIGHTS
    validate_weights({"price": 0.333, "duration": 0.333, "flexibility": 0.334})  # rounding is tolerated
    validate_weights({"price": 1})  # an int is fine


@pytest.mark.parametrize("weights, message", [
    ({}, "no criterion weights"),
    ({"price": 0.5, "duration": 0.45}, "must total 1.0"),
    ({"price": 0.6, "duration": 0.45}, "must total 1.0"),
    ({"price": 1.2, "duration": -0.2}, "cannot be negative"),
    ({"price": 0.5, "comfort": 0.5}, "unknown criterion 'comfort'"),
    ({"price": "0.5", "duration": 0.5}, "must be a number"),
    ({"price": True}, "must be a number"),
    ({"price": float("nan")}, "must be a number"),
], ids=str)
def test_invalid_weights_are_rejected(weights: dict, message: str) -> None:
    with pytest.raises(InvalidWeightsError, match=message):
        validate_weights(weights)


def test_ranking_rejects_request_without_weights(offer: Offer) -> None:
    with pytest.raises(InvalidWeightsError):
        rank_offers([offer], dataclasses.replace(REQUEST, weights={}))


# --- Totals and order --------------------------------------------------------

def test_worked_example_totals_and_order(worked_example: list[Offer]) -> None:
    ranking = rank_offers(worked_example, REQUEST)
    assert [(r.offer.offer_id, r.total) for r in ranking.offers] == [
        ("OF-SOL-MAL-0002", 83.9),  # B: on time and fully flexible beats cheaper A
        ("OF-SOL-MAL-0001", 77.9),  # A
        ("OF-SOL-MAL-0003", 61.2),  # C
    ]
    assert [r.rank for r in ranking.offers] == [1, 2, 3]
    assert ranking.top.offer.offer_id == "OF-SOL-MAL-0002"


def test_scores_are_kept_per_criterion(worked_example: list[Offer]) -> None:
    b = rank_offers(worked_example, REQUEST).top
    scores = {s.criterion: round(s.score, 1) for s in b.scores}
    assert scores == {"price": 66.7, "duration": 88.9, "departure": 100.0, "flexibility": 100.0}
    assert sum(s.contribution for s in b.scores) == pytest.approx(83.89, abs=0.01)


def test_weights_change_the_winner(worked_example: list[Offer]) -> None:
    budget = dataclasses.replace(REQUEST, weights={"price": 0.8, "duration": 0.1, "flexibility": 0.1})
    assert rank_offers(worked_example, budget).top.offer.offer_id == "OF-SOL-MAL-0001"  # A, cheapest
    fast = dataclasses.replace(REQUEST, weights={"duration": 0.8, "price": 0.2})
    assert rank_offers(worked_example, fast).top.offer.offer_id == "OF-SOL-MAL-0003"  # C, fastest


def test_zero_weight_criterion_is_shown_but_has_no_effect(worked_example: list[Offer]) -> None:
    weights = {"price": 1.0, "departure": 0.0}
    ranking = rank_offers(worked_example, dataclasses.replace(REQUEST, weights=weights))
    assert [c.name for c in ranking.criteria] == ["price", "departure"]
    assert [r.offer.price_eur for r in ranking.offers] == [30.0, 45.0, 49.5]


def test_totals_stay_between_0_and_100(worked_example: list[Offer]) -> None:
    for ranked in rank_offers(worked_example, REQUEST).offers:
        assert 0 <= ranked.total <= 100


def test_empty_input() -> None:
    ranking = rank_offers([], REQUEST)
    assert ranking.offers == () and ranking.top is None


# --- Ties and reproducibility ------------------------------------------------

def test_equal_totals_share_rank_and_follow_tie_break_order(offer: Offer) -> None:
    twin_a = dataclasses.replace(offer, offer_id="OF-SOL-MAL-0009")
    twin_b = dataclasses.replace(offer, offer_id="OF-SOL-MAL-0005")
    worse = dataclasses.replace(offer, offer_id="OF-SOL-MAL-0001", price_eur=60.0)
    ranking = rank_offers([twin_a, worse, twin_b], dataclasses.replace(REQUEST, weights={"price": 1.0}))
    assert [(r.rank, r.offer.offer_id) for r in ranking.offers] == [
        (1, "OF-SOL-MAL-0005"),  # tied: ordered by offer ID as the last tie-break
        (1, "OF-SOL-MAL-0009"),
        (3, "OF-SOL-MAL-0001"),  # competition ranking: 1, 1, 3
    ]


def test_tie_is_broken_by_price_first(offer: Offer) -> None:
    # Same total with only flexibility weighted, different prices: cheaper first.
    expensive = dataclasses.replace(offer, offer_id="OF-SOL-MAL-0001", price_eur=40.0)
    cheap = dataclasses.replace(offer, offer_id="OF-SOL-MAL-0002", price_eur=30.0)
    ranking = rank_offers([expensive, cheap], dataclasses.replace(REQUEST, weights={"flexibility": 1.0}))
    assert [r.offer.offer_id for r in ranking.offers] == ["OF-SOL-MAL-0002", "OF-SOL-MAL-0001"]


def test_same_input_in_any_order_gives_same_ranking(worked_example: list[Offer]) -> None:
    expected = [(r.offer.offer_id, r.total) for r in rank_offers(worked_example, REQUEST).offers]
    shuffled = worked_example[:]
    random.Random(1).shuffle(shuffled)
    assert [(r.offer.offer_id, r.total) for r in rank_offers(shuffled, REQUEST).offers] == expected


# --- Missing values ------------------------------------------------------------

def test_missing_value_gets_median_score_and_is_marked(offer: Offer) -> None:
    offers = [dataclasses.replace(offer, offer_id=f"OF-SOL-MAL-000{i}", co2_kg=co2)
              for i, co2 in enumerate([10.0, 20.0, 40.0, None], start=1)]
    ranking = rank_offers(offers, dataclasses.replace(REQUEST, weights={"emissions": 1.0}))
    scores = {r.offer.offer_id: r.scores[0] for r in ranking.offers}
    missing = scores["OF-SOL-MAL-0004"]
    assert missing.missing and missing.raw is None
    assert missing.score == pytest.approx(50.0)  # median of 100, 50, 25
    assert not scores["OF-SOL-MAL-0001"].missing


def test_all_values_missing_gives_everyone_the_neutral_score(worked_example: list[Offer]) -> None:
    request = dataclasses.replace(REQUEST, preferred_departure=None, weights={"departure": 1.0})
    ranking = rank_offers(worked_example, request)
    assert {r.total for r in ranking.offers} == {50.0}


def test_table_shows_values_scores_and_missing_marker(offer: Offer) -> None:
    offers = [offer, dataclasses.replace(offer, offer_id="OF-SOL-MAL-0002", co2_kg=None)]
    offers[0].co2_kg = 15.9
    weights = {"price": 0.5, "emissions": 0.5}
    table = rank_offers(offers, dataclasses.replace(REQUEST, weights=weights)).table()
    assert "Weights: price 50%, emissions 50%" in table
    assert "15.9 (100)" in table
    assert "n/a* (100)" in table  # median of the one known score
    assert "* value missing" in table


# --- Real data -----------------------------------------------------------------

def test_spec_example_on_real_data_is_reproducible(tmp_path) -> None:
    settings = dataclasses.replace(load_settings(), review_file=tmp_path / "rejected.csv")
    repository, _ = load_marketplace(settings)
    request = dataclasses.replace(REQUEST, max_budget_eur=50.0, max_transfers=1, require_changeable=True)
    accepted = filter_offers(repository.offers_to("MAL"), request).accepted

    first = rank_offers(accepted, request)
    second = rank_offers(list(reversed(accepted)), request)

    assert len(first.offers) == 15
    assert [(r.offer.offer_id, r.total) for r in first.offers] == [(r.offer.offer_id, r.total) for r in second.offers]
    totals = [r.total for r in first.offers]
    assert totals == sorted(totals, reverse=True)

"""Tests for the generated explanation of the top-ranked offer."""

import dataclasses
from datetime import date, datetime, time, timedelta

import pytest

from busbidder.models import FareConditions, FareType, Offer, TravellerRequest
from busbidder.ranking import explain_top, rank_offers

SPEC_WEIGHTS = {"price": 0.40, "duration": 0.25, "departure": 0.15, "flexibility": 0.20}
REQUEST = TravellerRequest("MAL", date(2026, 7, 12), date(2026, 7, 14),
                           preferred_departure=time(9, 0), weights=SPEC_WEIGHTS)
STANDARD = FareConditions(FareType.STANDARD, True, False, 20)
FLEX = FareConditions(FareType.FLEX, True, True, 30)


def make(offer: Offer, offer_id: str, price: float, departs: str, minutes: int, fare: FareConditions) -> Offer:
    departure = datetime.combine(date(2026, 7, 12), time.fromisoformat(departs))
    return dataclasses.replace(offer, offer_id=offer_id, price_eur=price, departure=departure,
                               arrival=departure + timedelta(minutes=minutes), fare=fare)


@pytest.fixture
def worked_example(offer: Offer) -> list[Offer]:
    """A (cheap, slow), B (on time, flexible), C (fast, late) from the ranking discussion. B wins."""
    return [
        make(offer, "OF-SOL-MAL-0001", 30.00, "12:15", 7 * 60, STANDARD),
        make(offer, "OF-SOL-MAL-0002", 45.00, "09:00", 6 * 60, FLEX),
        make(offer, "OF-SOL-MAL-0003", 49.50, "15:00", 5 * 60 + 20, STANDARD),
    ]


def test_no_offers_no_explanation() -> None:
    assert explain_top(rank_offers([], REQUEST)) is None


def test_advantages_and_disadvantages_come_from_the_data(worked_example: list[Offer]) -> None:
    explanation = explain_top(rank_offers(worked_example, REQUEST))
    assert explanation.offer.offer.offer_id == "OF-SOL-MAL-0002"
    # Most important criterion first (flexibility 20% before departure 15%).
    assert explanation.advantages == (
        "flexibility: changeable and refundable ticket",
        "departure: departs at your preferred time",
    )
    assert explanation.disadvantages == ("price: EUR 45.00, EUR 15.00 more than the cheapest acceptable offer",)
    # Duration (89 vs best 100) is between the two thresholds, so it is not mentioned.
    assert not any(text.startswith("duration") for text in explanation.advantages + explanation.disadvantages)


def test_comparison_with_runner_up(worked_example: list[Offer]) -> None:
    comparison = explain_top(rank_offers(worked_example, REQUEST)).comparison
    assert comparison == (
        "Compared with #2 (OF-SOL-MAL-0001, SolRuta, 77.9): 6.0 points ahead; "
        "gains on departure (+8.1), flexibility (+8.0), duration (+3.2); loses on price (-13.3)."
    )


def test_small_lead_is_called_out(offer: Offer) -> None:
    offers = [offer, dataclasses.replace(offer, offer_id="OF-SOL-MAL-0002", price_eur=33.0)]
    comparison = explain_top(rank_offers(offers, dataclasses.replace(REQUEST, weights={"price": 1.0}))).comparison
    assert "1.5 points ahead" in comparison
    assert "could change the order" in comparison


def test_tie_is_explained_as_tie_break(offer: Offer) -> None:
    offers = [offer, dataclasses.replace(offer, offer_id="OF-SOL-MAL-0002")]
    comparison = explain_top(rank_offers(offers, REQUEST)).comparison
    assert "tied on score" in comparison


def test_single_offer(offer: Offer) -> None:
    assert "only acceptable offer" in explain_top(rank_offers([offer], REQUEST)).comparison


def test_a_score_everyone_shares_is_not_praised(worked_example: list[Offer]) -> None:
    # Preferred time 02:00: every offer is 6 hours or more away, so all score 0.
    request = dataclasses.replace(REQUEST, preferred_departure=time(2, 0))
    explanation = explain_top(rank_offers(worked_example, request))
    assert not any(text.startswith("departure") for text in explanation.advantages)
    assert any(text.startswith("departure") for text in explanation.disadvantages)


def test_criterion_without_any_values_is_not_mentioned(worked_example: list[Offer]) -> None:
    explanation = explain_top(rank_offers(worked_example, dataclasses.replace(REQUEST, preferred_departure=None)))
    assert not any("departure" in text for text in explanation.advantages + explanation.disadvantages)


def test_zero_weight_criterion_is_not_mentioned(worked_example: list[Offer]) -> None:
    request = dataclasses.replace(REQUEST, weights={"price": 1.0, "flexibility": 0.0})
    explanation = explain_top(rank_offers(worked_example, request))
    assert not any("flexibility" in text for text in explanation.advantages + explanation.disadvantages)


def test_missing_value_is_listed_as_disadvantage(offer: Offer) -> None:
    unreported = dataclasses.replace(offer, offer_id="OF-NOC-MAL-0001", price_eur=20.0, co2_kg=None)
    reported = dataclasses.replace(offer, offer_id="OF-VER-MAL-0001", price_eur=40.0, co2_kg=6.0)
    request = dataclasses.replace(REQUEST, weights={"price": 0.6, "emissions": 0.4})
    explanation = explain_top(rank_offers([unreported, reported], request))
    assert explanation.offer.offer.offer_id == "OF-NOC-MAL-0001"
    assert "emissions: CO2 not reported by the company (given a neutral score)" in explanation.disadvantages


def test_text_has_all_parts_and_the_caveat(worked_example: list[Offer]) -> None:
    text = explain_top(rank_offers(worked_example, REQUEST)).text()
    assert text.startswith("Recommended: OF-SOL-MAL-0002, SolRuta, 12 Jul 09:00 -> 12 Jul 15:00, EUR 45.00")
    assert "  + flexibility: changeable and refundable ticket" in text
    assert "Remaining disadvantages:" in text
    assert "Not part of the score: direct, no transfers; 30 kg luggage included" in text
    assert "price 40%, duration 25%, departure 15%, flexibility 20%" in text
    assert "not objectively the best offer" in text

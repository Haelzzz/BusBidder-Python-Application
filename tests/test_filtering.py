"""Tests for the filter engine: splitting offers, explanations and the summary."""

import dataclasses
from datetime import date

import pytest

from busbidder.data_io.loader import load_marketplace
from busbidder.filtering import filter_offers
from busbidder.models import FareConditions, FareType, Offer, TravellerRequest
from busbidder.settings import load_settings

REQUEST = TravellerRequest("MAL", date(2026, 7, 12), date(2026, 7, 14))


@pytest.fixture
def offers(offer: Offer) -> list[Offer]:
    """Four offers: the fixture offer, a too expensive one, a basic fare, and one breaking two constraints."""
    expensive = dataclasses.replace(offer, offer_id="OF-SOL-MAL-0002", price_eur=60.0)
    basic = dataclasses.replace(offer, offer_id="OF-SOL-MAL-0003",
                                fare=FareConditions(FareType.BASIC, False, False, 10))
    both = dataclasses.replace(basic, offer_id="OF-SOL-MAL-0004", price_eur=70.0)
    return [offer, expensive, basic, both]


def test_without_optional_constraints_only_core_ones_apply(offers: list[Offer]) -> None:
    result = filter_offers(offers, REQUEST)
    assert [c.name for c in result.constraints] == ["destination", "travel_window", "seats"]
    assert len(result.accepted) == 4 and not result.rejected


def test_offers_are_split_and_all_violations_listed(offers: list[Offer]) -> None:
    request = dataclasses.replace(REQUEST, max_budget_eur=50.0, require_changeable=True)
    result = filter_offers(offers, request)

    assert [o.offer_id for o in result.accepted] == ["OF-SOL-MAL-0001"]
    reasons = {r.offer.offer_id: [v.constraint for v in r.violations] for r in result.rejected}
    assert reasons == {
        "OF-SOL-MAL-0002": ["budget"],
        "OF-SOL-MAL-0003": ["changeable"],
        "OF-SOL-MAL-0004": ["budget", "changeable"],  # both reasons, not just the first
    }


def test_counts_per_constraint(offers: list[Offer]) -> None:
    request = dataclasses.replace(REQUEST, max_budget_eur=50.0, require_changeable=True)
    result = filter_offers(offers, request)
    assert result.removed_by() == {"budget": 2, "changeable": 2}
    assert result.blocked_only_by() == {"budget": 1, "changeable": 1}


def test_explanation_is_readable(offers: list[Offer]) -> None:
    request = dataclasses.replace(REQUEST, max_budget_eur=50.0, require_changeable=True)
    rejected = {r.offer.offer_id: r for r in filter_offers(offers, request).rejected}
    assert rejected["OF-SOL-MAL-0004"].explain() == (
        "budget: costs EUR 70.00; changeable: basic fare is not changeable"
    )


def test_summary_lists_active_constraints_and_counts(offers: list[Offer]) -> None:
    request = dataclasses.replace(REQUEST, max_budget_eur=50.0)
    summary = filter_offers(offers, request).summary()
    assert "budget         total price at most EUR 50.00" in summary
    assert "changeable" not in summary  # not requested, so not shown as a constraint
    assert "Checked 4 offers: 2 acceptable, 2 removed." in summary


def test_no_acceptable_offer_suggests_what_to_relax(offers: list[Offer]) -> None:
    request = dataclasses.replace(REQUEST, max_budget_eur=10.0, require_changeable=True)
    summary = filter_offers(offers, request).summary()
    assert "No offer meets all hard constraints." in summary
    assert "Relaxing 'budget' alone would make 2 offer(s) acceptable." in summary


def test_no_relaxation_hint_when_every_offer_breaks_several(offers: list[Offer]) -> None:
    request = dataclasses.replace(REQUEST, max_budget_eur=10.0, max_duration_min=60)
    summary = filter_offers(offers, request).summary()
    assert "Every removed offer breaks more than one constraint." in summary


def test_empty_input() -> None:
    result = filter_offers([], REQUEST)
    assert result.accepted == () and result.rejected == ()
    assert "Checked 0 offers" in result.summary()
    assert "No offer meets" not in result.summary()


def test_filtering_does_not_change_offers(offers: list[Offer]) -> None:
    before = [dataclasses.asdict(o) for o in offers]
    filter_offers(offers, dataclasses.replace(REQUEST, max_budget_eur=10.0))
    assert [dataclasses.asdict(o) for o in offers] == before


def test_spec_example_on_real_data(tmp_path) -> None:
    """Madrid-Malaga, 12-14 July, EUR 50, at most 1 transfer, changeable ticket."""
    settings = dataclasses.replace(load_settings(), review_file=tmp_path / "rejected.csv")
    repository, _ = load_marketplace(settings)
    request = dataclasses.replace(REQUEST, max_budget_eur=50.0, max_transfers=1, require_changeable=True)

    result = filter_offers(repository.offers_to("MAL"), request)

    assert len(result.accepted) == 15
    for offer in result.accepted:
        assert request.covers(offer.travel_date)
        assert offer.price_eur <= 50 and offer.transfers <= 1 and offer.fare.changeable

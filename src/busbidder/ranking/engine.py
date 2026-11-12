"""Weighted multi-criteria ranking of the offers that passed filtering.

    total(offer) = sum over criteria of weight * score(offer)

Scores are 0-100 with 100 best, and weights must total 1.0, so totals are
also 0-100. The policies below apply to every criterion the same way:

- Missing values get the median score of the other offers for that criterion
  (50 if none is known): neutral, neither punished nor rewarded, and marked as
  missing in the output. Punishing them would hit companies that do not
  publish an optional figure, rather than offers that are actually worse.
- Ties: totals are rounded to one decimal; equal totals share a rank and are
  ordered by price, then departure, then offer ID, so the result is always the
  same for the same input.
"""

import logging
import math
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import busbidder.ranking.criteria  
from busbidder.exceptions import InvalidWeightsError
from busbidder.models import Offer, TravellerRequest
from busbidder.ranking.base import CRITERIA, Criterion

logger = logging.getLogger(__name__)

WEIGHT_TOLERANCE = 0.001  
NEUTRAL_SCORE = 50.0  


@dataclass(frozen=True, slots=True)
class CriterionScore:
    """One criterion's result for one offer."""

    criterion: str
    raw: float | None  
    score: float  
    weight: float

    @property
    def missing(self) -> bool:
        return self.raw is None

    @property
    def contribution(self) -> float:
        """Points this criterion adds to the total."""
        return self.weight * self.score


@dataclass(frozen=True, slots=True)
class RankedOffer:
    rank: int  
    offer: Offer
    total: float  
    scores: tuple[CriterionScore, ...]


@dataclass(frozen=True, slots=True)
class Ranking:
    """The ranked offers, with the criteria and weights that produced the order."""

    request: TravellerRequest
    criteria: tuple[Criterion, ...]
    weights: Mapping[str, float]
    offers: tuple[RankedOffer, ...]

    @property
    def top(self) -> RankedOffer | None:
        return self.offers[0] if self.offers else None

    def table(self) -> str:
        """The ranking as a text table: raw value and (score) per criterion, and the total."""
        weights = ", ".join(f"{c.name} {self.weights[c.name]:.0%}" for c in self.criteria)
        lines = [f"Weights: {weights}"]
        header = f"{'#':>3}  {'Offer':<17}{'Company':<16}{'Departs':<14}"
        header += "".join(f"{c.label:>16}" for c in self.criteria) + f"{'Total':>8}"
        lines.append(header)
        for ranked in self.offers:
            row = (f"{ranked.rank:>3}  {ranked.offer.offer_id:<17}{ranked.offer.company.name:<16}"
                   f"{ranked.offer.departure:%d %b %H:%M}  ")
            for criterion, result in zip(self.criteria, ranked.scores):
                value = "n/a*" if result.missing else criterion.format_raw(result.raw)
                row += f"{value} ({result.score:.0f})".rjust(16)
            lines.append(row + f"{ranked.total:>8.1f}")
        if any(s.missing for r in self.offers for s in r.scores):
            lines.append("* value missing or not applicable: given the median score of the other offers")
        return "\n".join(lines)


def validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Check that every weight names a criterion, is a non-negative number, and that they total 1.0."""
    if not weights:
        raise InvalidWeightsError("no criterion weights given")
    checked: dict[str, float] = {}
    for name, weight in weights.items():
        if name not in CRITERIA:
            raise InvalidWeightsError(f"unknown criterion {name!r} (known: {', '.join(CRITERIA.names())})")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
            raise InvalidWeightsError(f"weight for {name!r} must be a number, got {weight!r}")
        if weight < 0:
            raise InvalidWeightsError(f"weight for {name!r} cannot be negative, got {weight}")
        checked[name] = float(weight)
    total = sum(checked.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise InvalidWeightsError(f"weights must total 1.0 (100%), got {total:.3f}")
    return checked


def rank_offers(offers: Iterable[Offer], request: TravellerRequest) -> Ranking:
    """Rank ``offers`` (already filtered) using the weights in ``request``."""
    weights = validate_weights(request.weights)
    criteria = tuple(CRITERIA.create(name) for name in CRITERIA.names() if name in weights)
    offers = list(offers)

    columns = [_score_column(criterion, offers, request, weights[criterion.name]) for criterion in criteria]
    rows = []
    for i, offer in enumerate(offers):
        scores = tuple(column[i] for column in columns)
        rows.append((offer, round(sum(s.contribution for s in scores), 1), scores))
    rows.sort(key=lambda row: (-row[1], row[0].price_eur, row[0].departure, row[0].offer_id))

    ranked: list[RankedOffer] = []
    for position, (offer, total, scores) in enumerate(rows, start=1):
        rank = ranked[-1].rank if ranked and ranked[-1].total == total else position
        ranked.append(RankedOffer(rank, offer, total, scores))

    logger.info("Ranked %d offers for %s with weights %s", len(ranked), request.destination_id, weights)
    return Ranking(request, criteria, weights, tuple(ranked))


def _score_column(
    criterion: Criterion, offers: list[Offer], request: TravellerRequest, weight: float,
) -> list[CriterionScore]:
    raws = [criterion.raw_value(offer, request) for offer in offers]
    scores = criterion.normalise(raws)
    known = [score for score in scores if score is not None]
    neutral = statistics.median(known) if known else NEUTRAL_SCORE
    return [
        CriterionScore(criterion.name, raw, neutral if score is None else score, weight)
        for raw, score in zip(raws, scores)
    ]

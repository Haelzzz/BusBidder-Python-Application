"""Explains why the top-ranked offer is recommended, using only the ranking data.

For each weighted criterion (most important first), the top offer's score is
compared with the best score among the acceptable offers:

- advantage: within ADVANTAGE_GAP points of the best, and a reasonable score
  in itself (at least GOOD_SCORE), so "everyone is bad" is not praised;
- disadvantage: DISADVANTAGE_GAP or more points behind the best, or a low
  score in itself;
- otherwise not mentioned, to keep the explanation short.

It also compares the winner with the runner-up, criterion by criterion, and
always states that the result depends on the chosen constraints and weights.
"""

from dataclasses import dataclass

from busbidder.ranking.engine import RankedOffer, Ranking

ADVANTAGE_GAP = 10.0
DISADVANTAGE_GAP = 15.0
GOOD_SCORE = 50.0
CLOSE_MARGIN = 2.0  # a lead smaller than this is called out as fragile
SHORT_CAVEAT = "Recommended for these priorities; other priorities can give a different choice."


@dataclass(frozen=True, slots=True)
class Point:
    """One advantage or disadvantage, e.g. ("flexibility", "changeable and refundable ticket")."""

    criterion: str
    text: str

    def __str__(self) -> str:
        return f"{self.criterion}: {self.text}"


@dataclass(frozen=True, slots=True)
class Explanation:
    offer: RankedOffer
    advantages: tuple[Point, ...]
    disadvantages: tuple[Point, ...]
    comparison: str
    other_facts: tuple[str, ...]  # shown for context; not part of the score
    caveat: str

    def text(self) -> str:
        o = self.offer.offer
        lines = [
            f"Recommended: {o.offer_id}, {o.company.name}, {o.departure:%d %b %H:%M} -> "
            f"{o.arrival:%d %b %H:%M}, EUR {o.price_eur:.2f} (score {self.offer.total:.1f})",
            "Advantages:",
        ]
        lines += [f"  + {a}" for a in self.advantages] or ["  (no single standout: a compromise across the criteria)"]
        if self.disadvantages:
            lines.append("Remaining disadvantages:")
            lines += [f"  - {d}" for d in self.disadvantages]
        lines.append(self.comparison)
        lines.append("Not part of the score: " + "; ".join(self.other_facts) + ".")
        lines.append(self.caveat)
        return "\n".join(lines)


def explain_top(ranking: Ranking) -> Explanation | None:
    """Explain the highest-ranked offer, or return ``None`` if nothing was ranked."""
    top = ranking.top
    if top is None:
        return None

    advantages: list[Point] = []
    disadvantages: list[Point] = []
    by_importance = sorted(range(len(ranking.criteria)), key=lambda i: -ranking.weights[ranking.criteria[i].name])
    for i in by_importance:
        criterion = ranking.criteria[i]
        if ranking.weights[criterion.name] == 0:
            continue
        result = top.scores[i]
        known = [r.scores[i] for r in ranking.offers if not r.scores[i].missing]
        if not known:
            continue  # no offer has a value (e.g. no preferred time): not applicable
        if result.missing:
            disadvantages.append(Point(criterion.name, criterion.describe_missing()))
            continue

        best = max(known, key=lambda s: s.score)
        gap = best.score - result.score
        phrase = Point(criterion.name, criterion.describe(result.raw, best.raw))
        if gap <= ADVANTAGE_GAP and result.score >= GOOD_SCORE:
            advantages.append(phrase)
        elif gap >= DISADVANTAGE_GAP or result.score < GOOD_SCORE:
            disadvantages.append(phrase)

    weights = ", ".join(f"{c.name} {ranking.weights[c.name]:.0%}" for c in ranking.criteria)
    caveat = (f"This is the best match under the hard constraints and weights used ({weights}). "
              "It is not objectively the best offer: different weights can give a different recommendation.")
    return Explanation(top, tuple(advantages), tuple(disadvantages), _compare_with_runner_up(ranking),
                       _other_facts(top), caveat)


def _compare_with_runner_up(ranking: Ranking) -> str:
    top = ranking.offers[0]
    if len(ranking.offers) == 1:
        return "It is the only acceptable offer, so there is nothing to compare it with."
    second = ranking.offers[1]
    text = f"Compared with #2 ({second.offer.offer_id}, {second.offer.company.name}, {second.total:.1f}): "
    if second.total == top.total:
        return text + "tied on score; listed first only because of the tie-break (lower price, then earlier departure)."

    differences = [
        (criterion.name, a.contribution - b.contribution)
        for criterion, a, b in zip(ranking.criteria, top.scores, second.scores)
    ]
    gains = [f"{name} (+{d:.1f})" for name, d in sorted(differences, key=lambda x: -x[1]) if d >= 0.05]
    losses = [f"{name} ({d:.1f})" for name, d in sorted(differences, key=lambda x: x[1]) if d <= -0.05]
    margin = top.total - second.total
    parts = [f"{margin:.1f} points ahead"]
    if gains:
        parts.append("gains on " + ", ".join(gains))
    if losses:
        parts.append("loses on " + ", ".join(losses))
    text += "; ".join(parts) + "."
    if margin < CLOSE_MARGIN:
        text += f" The lead is under {CLOSE_MARGIN:g} points, so a small change in weights could change the order."
    return text


def _other_facts(ranked: RankedOffer) -> tuple[str, ...]:
    offer = ranked.offer
    return (
        "direct, no transfers" if offer.is_direct else f"{offer.transfers} transfer(s)",
        f"{offer.fare.luggage_kg} kg luggage included",
        f"{offer.available_seats} seat(s) left",
        f"customer rating {offer.rating:.1f}",
    )

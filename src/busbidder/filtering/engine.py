"""Removes offers that break the traveller's hard constraints.

Every active constraint is checked for every offer, so a rejected offer lists
all the constraints it breaks, not only the first. (Data validation stops at the
first problem instead; there, one clean category per record matters more than
a full explanation.)
"""

import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

import busbidder.filtering.constraints  # noqa: F401  (registers the built-in constraints)
from busbidder.filtering.base import CONSTRAINTS, Constraint
from busbidder.models import Offer, TravellerRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Violation:
    constraint: str  # registered constraint name
    reason: str


@dataclass(frozen=True, slots=True)
class RejectedOffer:
    offer: Offer
    violations: tuple[Violation, ...]

    def explain(self) -> str:
        return "; ".join(f"{v.constraint}: {v.reason}" for v in self.violations)


@dataclass(frozen=True, slots=True)
class FilterResult:
    """Outcome of filtering: the active constraints, and which offers passed or not."""

    request: TravellerRequest
    constraints: tuple[Constraint, ...]  # only the active ones, in registration order
    accepted: tuple[Offer, ...]
    rejected: tuple[RejectedOffer, ...]

    def removed_by(self) -> Counter[str]:
        """Offers removed per constraint. An offer breaking two constraints counts for both."""
        return Counter(v.constraint for r in self.rejected for v in r.violations)

    def blocked_only_by(self) -> Counter[str]:
        """Offers for which a constraint is the only obstacle, i.e. would pass if it were relaxed."""
        return Counter(r.violations[0].constraint for r in self.rejected if len(r.violations) == 1)

    def summary(self) -> str:
        lines = ["Hard constraints (an offer must meet all of them):"]
        lines += [f"  {c.name:<15}{c.requirement(self.request)}" for c in self.constraints]
        total = len(self.accepted) + len(self.rejected)
        lines.append(f"Checked {total} offers: {len(self.accepted)} acceptable, {len(self.rejected)} removed.")

        removed = self.removed_by()
        if removed:
            lines.append("Removed by (an offer can break several constraints):")
            lines += [f"  {c.name:<15}{removed[c.name]:>5}" for c in self.constraints if removed[c.name]]

        if total and not self.accepted:
            lines.append("No offer meets all hard constraints.")
            blocked = self.blocked_only_by()
            if blocked:
                name, count = blocked.most_common(1)[0]
                lines.append(f"Relaxing '{name}' alone would make {count} offer(s) acceptable.")
            else:
                lines.append("Every removed offer breaks more than one constraint.")
        return "\n".join(lines)


def filter_offers(offers: Iterable[Offer], request: TravellerRequest) -> FilterResult:
    """Split ``offers`` into those meeting every active hard constraint and those that do not."""
    constraints = tuple(
        constraint
        for constraint in (CONSTRAINTS.create(name) for name in CONSTRAINTS.names())
        if constraint.is_active(request)
    )
    accepted: list[Offer] = []
    rejected: list[RejectedOffer] = []
    for offer in offers:
        violations = tuple(
            Violation(constraint.name, reason)
            for constraint in constraints
            if (reason := constraint.violation(offer, request)) is not None
        )
        if violations:
            rejected.append(RejectedOffer(offer, violations))
        else:
            accepted.append(offer)

    logger.info("Filtered %d offers for %s (%s): %d acceptable, %d removed",
                len(accepted) + len(rejected), request.destination_id,
                ", ".join(c.name for c in constraints), len(accepted), len(rejected))
    return FilterResult(request, constraints, tuple(accepted), tuple(rejected))

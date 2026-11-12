"""Base classes and registry for ranking criteria.

A criterion measures one aspect of an offer in its own unit (euros, minutes,
...) and converts those raw values to scores from 0 to 100, where 100 is always
best for the traveller. Only then can criteria be combined with weights.

Two ways of scaling, as two subclasses:

- ``RatioToBestCriterion``: lower is better, scored relative to the best offer
  (``100 * best / value``). Differences keep their real proportions, so a small
  price difference gives a small score difference.
- ``FixedScaleCriterion``: each raw value has a fixed score that does not depend
  on the other offers (e.g. "3 hours from the preferred time").

Missing values stay ``None`` here; how to score them is a policy decided by the
ranking engine, the same for every criterion.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from busbidder.models import Offer, TravellerRequest
from busbidder.registry import Registry


class Criterion(ABC):
    """One measurable aspect of an offer used in the weighted score."""

    name: ClassVar[str] = "" 
    label: ClassVar[str] = ""  

    @abstractmethod
    def raw_value(self, offer: Offer, request: TravellerRequest) -> float | None:
        """Return the raw measurement for ``offer``, or ``None`` if it is missing."""

    @abstractmethod
    def normalise(self, raw_values: Sequence[float | None]) -> list[float | None]:
        """Scores 0-100 for the raw values of all offers being ranked; ``None`` stays ``None``."""

    def format_raw(self, raw: float) -> str:
        """The raw value as shown to the user."""
        return f"{raw:g}"

    @abstractmethod
    def describe(self, raw: float, best_raw: float) -> str:
        """A phrase for the explanation, comparing ``raw`` with the best acceptable offer's value."""

    def describe_missing(self) -> str:
        """A phrase for the explanation when the offer has no value."""
        return f"{self.label.lower()} not available"


class RatioToBestCriterion(Criterion):
    """Lower is better. The best offer scores 100; twice the best value scores 50."""

    def normalise(self, raw_values: Sequence[float | None]) -> list[float | None]:
        known = [value for value in raw_values if value is not None]
        if not known:
            return [None] * len(raw_values)
        best = min(known)
        return [
            None if value is None else 100.0 if value == best else 100.0 * best / value
            for value in raw_values
        ]


class FixedScaleCriterion(Criterion):
    """Each raw value has its own fixed score, independent of the other offers."""

    @abstractmethod
    def score(self, raw: float) -> float:
        """Score 0-100 for one raw value."""

    def normalise(self, raw_values: Sequence[float | None]) -> list[float | None]:
        return [None if value is None else self.score(value) for value in raw_values]


CRITERIA: Registry[Criterion] = Registry("criterion", Criterion)

"""Base class and registry for ranking criteria.

Each criterion measures one aspect of an offer (price, duration, ...) in its
own raw unit. Normalising raw values to a common scale and applying weights is
the ranking engine's job (later task), so criteria stay small and comparable.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from busbidder.models import Offer, TravellerRequest
from busbidder.registry import Registry


class Criterion(ABC):
    """One measurable aspect of an offer used in the weighted score."""

    name: ClassVar[str] = ""  # set by @CRITERIA.register(...)
    higher_is_better: ClassVar[bool] = False  # e.g. False for price, True for rating
    description: ClassVar[str] = ""

    @abstractmethod
    def raw_value(self, offer: Offer, request: TravellerRequest) -> float | None:
        """Return the raw measurement for ``offer``, or ``None`` if it is missing."""


CRITERIA: Registry[Criterion] = Registry("criterion", Criterion)

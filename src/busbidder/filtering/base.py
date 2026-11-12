"""Base class and registry for hard constraints.

A constraint either accepts an offer or explains why it is rejected, so the
user can see which mandatory condition removed each offer.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from busbidder.models import Offer, TravellerRequest
from busbidder.registry import Registry


class Constraint(ABC):
    """A mandatory condition an offer must satisfy before it can be ranked."""

    name: ClassVar[str] = ""  # set by @CONSTRAINTS.register(...)

    def is_active(self, request: TravellerRequest) -> bool:
        """Whether ``request`` sets this constraint.

        Constraints that define the request itself (destination, travel window,
        seats) keep this default and always apply. Optional ones apply only when
        the traveller has set a limit or requirement.
        """
        return True

    @abstractmethod
    def requirement(self, request: TravellerRequest) -> str:
        """What the constraint demands for ``request``, e.g. "total price at most EUR 50.00"."""

    @abstractmethod
    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        """Return ``None`` if ``offer`` satisfies the constraint, else a short reason."""


CONSTRAINTS: Registry[Constraint] = Registry("constraint", Constraint)

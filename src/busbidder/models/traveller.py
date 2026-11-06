"""What a traveller asks the marketplace for."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, time

from busbidder.exceptions import InvalidRequestError


@dataclass(frozen=True, slots=True)
class TravellerRequest:
    """A flexible travel request: constraints, preferences and criterion weights.

    ``None`` means "no requirement" for optional limits. Which fields act as hard
    constraints (filtering) and which as soft preferences (ranking) is decided
    by the filtering and ranking layers, not here.
    """

    destination_id: str
    earliest_date: date
    latest_date: date
    max_budget_eur: float | None = None
    preferred_departure: time | None = None
    max_transfers: int | None = None
    max_duration_min: int | None = None
    min_luggage_kg: int = 0
    require_changeable: bool = False
    require_refundable: bool = False
    seats: int = 1
    weights: Mapping[str, float] = field(default_factory=dict)  # criterion name -> weight
    traveller_name: str = ""

    def __post_init__(self) -> None:
        # The request is built from user input (CLI or profile file), so it is
        # checked here, at the point where it enters the program.
        if self.latest_date < self.earliest_date:
            raise InvalidRequestError(
                f"travel window ends ({self.latest_date}) before it starts ({self.earliest_date})"
            )
        if self.seats < 1:
            raise InvalidRequestError(f"seats must be at least 1, got {self.seats}")
        if self.max_budget_eur is not None and self.max_budget_eur < 0:
            raise InvalidRequestError(f"budget cannot be negative, got {self.max_budget_eur}")
        if self.max_transfers is not None and self.max_transfers < 0:
            raise InvalidRequestError(f"max transfers cannot be negative, got {self.max_transfers}")

    def covers(self, day: date) -> bool:
        """True if ``day`` lies inside the travel window (inclusive)."""
        return self.earliest_date <= day <= self.latest_date

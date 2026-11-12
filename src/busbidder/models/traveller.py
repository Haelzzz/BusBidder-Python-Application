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
        if self.max_duration_min is not None and self.max_duration_min <= 0:
            raise InvalidRequestError(f"max duration must be positive, got {self.max_duration_min}")
        if self.min_luggage_kg < 0:
            raise InvalidRequestError(f"luggage cannot be negative, got {self.min_luggage_kg}")

    def covers(self, day: date) -> bool:
        """True if ``day`` lies inside the travel window (inclusive)."""
        return self.earliest_date <= day <= self.latest_date


@dataclass(frozen=True, slots=True)
class Trip:
    """Where and when: the journey, independent of who travels.

    Budget and maximum duration belong here rather than in a profile, because
    their sensible values depend on the destination (Toledo is 1 hour away,
    Santiago 8).
    """

    destination_id: str
    earliest_date: date
    latest_date: date
    seats: int = 1
    max_budget_eur: float | None = None
    max_duration_min: int | None = None


@dataclass(frozen=True, slots=True)
class TravellerProfile:
    """Who travels: preferences, weights and requirements that hold for any destination.

    Loaded from config/profiles/*.json. Combined with a ``Trip`` it gives the
    ``TravellerRequest`` that filtering and ranking use, so the same trip can
    be compared across profiles.
    """

    key: str 
    name: str
    description: str
    weights: Mapping[str, float]
    preferred_departure: time | None = None
    max_transfers: int | None = None
    min_luggage_kg: int = 0
    require_changeable: bool = False
    require_refundable: bool = False

    def request_for(self, trip: Trip) -> TravellerRequest:
        return TravellerRequest(
            destination_id=trip.destination_id,
            earliest_date=trip.earliest_date,
            latest_date=trip.latest_date,
            max_budget_eur=trip.max_budget_eur,
            preferred_departure=self.preferred_departure,
            max_transfers=self.max_transfers,
            max_duration_min=trip.max_duration_min,
            min_luggage_kg=self.min_luggage_kg,
            require_changeable=self.require_changeable,
            require_refundable=self.require_refundable,
            seats=trip.seats,
            weights=self.weights,
            traveller_name=self.name,
        )

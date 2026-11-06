"""Bus offers and the fare conditions attached to them."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from busbidder.models.company import Company
from busbidder.models.destination import Destination


class FareType(StrEnum):
    """Fare families offered by the companies."""

    BASIC = "basic"
    STANDARD = "standard"
    FLEX = "flex"


@dataclass(frozen=True, slots=True)
class FareConditions:
    """The ticket rules of an offer.

    Kept as a separate immutable value object so a booking can store an exact
    copy of the conditions that applied when it was made.
    """

    fare_type: FareType
    changeable: bool
    refundable: bool
    luggage_kg: int  # included hold luggage


@dataclass(slots=True)
class Offer:
    """One bookable departure from Madrid to a destination.

    Composition: the offer owns its ``FareConditions``.
    Aggregation: ``company`` and ``destination`` are shared reference objects,
    resolved from their IDs when the data is loaded.

    Not frozen, because ``available_seats`` decreases when a booking is made.
    """

    offer_id: str  # e.g. "OF-SOL-MAL-0001"
    company: Company
    destination: Destination
    departure: datetime
    arrival: datetime
    price_eur: float
    transfers: int
    available_seats: int
    rating: float  # customer rating on the configured scale
    fare: FareConditions
    co2_kg: float | None = None  # estimated emissions per passenger (optional)

    @property
    def duration_min(self) -> int:
        """Journey time in minutes, derived from departure and arrival."""
        return int((self.arrival - self.departure).total_seconds() // 60)

    @property
    def travel_date(self) -> date:
        """The date of departure."""
        return self.departure.date()

    @property
    def is_direct(self) -> bool:
        return self.transfers == 0

    @property
    def is_overnight(self) -> bool:
        """True if the bus arrives on a later calendar day than it departs."""
        return self.arrival.date() > self.departure.date()

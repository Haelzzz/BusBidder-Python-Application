"""Simulated bookings."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from busbidder.models.offer import FareConditions


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    """Payment is only simulated; no payment details are ever collected."""

    SIMULATED_PAID = "simulated_paid"
    PENDING = "pending"


@dataclass(slots=True)
class Booking:
    """A confirmed reservation of seats on an offer.

    Refers to the offer by ID rather than holding the ``Offer`` object, because
    bookings are saved to file and must outlive a particular load of the offer
    data. The fare conditions are copied in as a snapshot so the booking keeps
    the rules that applied when it was made.
    """

    reference: str  # unique booking reference, e.g. "BB-7K2Q9X"
    offer_id: str
    traveller_name: str
    seats: int
    total_price_eur: float
    fare: FareConditions
    created_at: datetime
    status: BookingStatus = BookingStatus.CONFIRMED
    payment_status: PaymentStatus = PaymentStatus.SIMULATED_PAID

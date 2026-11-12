"""Simulated booking: confirm seats, create a unique reference, save, reduce capacity.

No real payment takes place and no payment details are asked for; a booking
is marked as paid (simulated).
"""

import logging
import secrets
from collections.abc import Callable
from datetime import datetime

from busbidder.booking.store import BookingStore
from busbidder.data_io.repository import MarketplaceRepository
from busbidder.exceptions import BookingError
from busbidder.models import Booking, BookingStatus, Offer
from busbidder.patterns import BOOKING_REF_ALPHABET

logger = logging.getLogger(__name__)

REFERENCE_LENGTH = 6
REFERENCE_ATTEMPTS = 100
MAX_NAME_LENGTH = 60


def new_reference() -> str:
    """A random booking reference such as "BB-7K2Q9X".

    ``secrets`` instead of ``random``: references should not be guessable, and
    unlike the dataset they do not need to be reproducible.
    """
    return "BB-" + "".join(secrets.choice(BOOKING_REF_ALPHABET) for _ in range(REFERENCE_LENGTH))


class BookingService:
    """Creates bookings and keeps seat counts consistent with the saved bookings."""

    def __init__(
        self,
        repository: MarketplaceRepository,
        store: BookingStore,
        *,
        clock: Callable[[], datetime] = datetime.now,
        make_reference: Callable[[], str] = new_reference,
    ) -> None:
        self._repository = repository
        self._store = store
        self._clock = clock
        self._make_reference = make_reference  # replaceable in tests
        self._bookings = store.load()
        self._apply_saved_bookings()

    @property
    def bookings(self) -> tuple[Booking, ...]:
        return tuple(self._bookings)

    def book(self, offer_id: str, traveller_name: str, seats: int) -> Booking:
        """Book ``seats`` on an offer. Raises ``BookingError`` if that is not possible."""
        offer = self._repository.find_offer(offer_id)
        if offer is None:
            raise BookingError(f"unknown offer {offer_id!r}")
        name = traveller_name.strip()
        if not name:
            raise BookingError("a traveller name is required")
        if len(name) > MAX_NAME_LENGTH:
            raise BookingError(f"the traveller name can be at most {MAX_NAME_LENGTH} characters")
        if seats < 1:
            raise BookingError(f"at least 1 seat must be booked, got {seats}")
        # Checked again here, not only by the filter: seats may have been taken since the search.
        if seats > offer.available_seats:
            raise BookingError(f"only {offer.available_seats} seat(s) left on {offer_id}")

        booking = Booking(
            reference=self._unique_reference(),
            offer_id=offer.offer_id,
            traveller_name=name,
            seats=seats,
            total_price_eur=round(offer.price_eur * seats, 2),
            fare=offer.fare,  # immutable, so this is a snapshot of the conditions sold
            created_at=self._clock().replace(microsecond=0),
        )
        # Save first: if saving fails, neither the booking list nor the seats change.
        self._store.save([*self._bookings, booking])
        self._bookings.append(booking)
        offer.available_seats -= seats
        logger.info("Booked %s: %d seat(s) on %s for %s, EUR %.2f; %d seat(s) left",
                    booking.reference, seats, offer_id, name, booking.total_price_eur, offer.available_seats)
        return booking

    def _unique_reference(self) -> str:
        used = {booking.reference for booking in self._bookings}
        for _ in range(REFERENCE_ATTEMPTS):
            reference = self._make_reference()
            if reference not in used:
                return reference
        raise BookingError("could not generate a unique booking reference")

    def _apply_saved_bookings(self) -> None:
        """Subtract the seats of saved, confirmed bookings from the freshly loaded offers."""
        applied = 0
        for booking in self._bookings:
            if booking.status is not BookingStatus.CONFIRMED:
                continue
            offer = self._repository.find_offer(booking.offer_id)
            if offer is None:
                logger.warning("Booking %s refers to offer %s, which is not in the data; seats not adjusted",
                               booking.reference, booking.offer_id)
                continue
            if booking.seats > offer.available_seats:
                logger.warning("Booking %s has %d seat(s) but offer %s only has %d; set to 0",
                               booking.reference, booking.seats, offer.offer_id, offer.available_seats)
                offer.available_seats = 0
            else:
                offer.available_seats -= booking.seats
            applied += 1
        logger.info("Applied %d saved booking(s) from %s", applied, self._store.path)


def format_confirmation(booking: Booking, offer: Offer) -> str:
    duration = f"{offer.duration_min // 60}h{offer.duration_min % 60:02d}"
    route = "direct" if offer.is_direct else f"{offer.transfers} transfer(s)"
    fare = booking.fare
    return "\n".join([
        f"Booking confirmed: {booking.reference}",
        f"  Traveller:  {booking.traveller_name}",
        f"  Journey:    Madrid -> {offer.destination.name} with {offer.company.name} ({offer.offer_id})",
        f"  Departs:    {offer.departure:%a %d %b %Y %H:%M}",
        f"  Arrives:    {offer.arrival:%a %d %b %Y %H:%M}  ({duration}, {route})",
        f"  Fare:       {fare.fare_type}; changeable: {'yes' if fare.changeable else 'no'}, "
        f"refundable: {'yes' if fare.refundable else 'no'}, luggage: {fare.luggage_kg} kg",
        f"  Seats:      {booking.seats}",
        f"  Total:      EUR {booking.total_price_eur:.2f} (payment simulated; no payment details collected)",
        f"  Booked at:  {booking.created_at:%Y-%m-%d %H:%M}",
    ])

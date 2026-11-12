"""Saves and reads the simulated bookings (a JSON list in bookings/bookings.json).

offers.csv is source data and is never modified. Booked seats are stored here
instead and subtracted from the offers when the program starts.

The file is the program's own state, so a corrupt file stops the program
(``DataFileError``) instead of being skipped: skipping bookings would silently
give wrong seat counts.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from busbidder.data_io.validator import parse_bool, parse_fare_type, parse_float, parse_int, parse_text
from busbidder.exceptions import BookingError, DataFileError, ErrorCategory, RecordValidationError
from busbidder.models import Booking, BookingStatus, FareConditions, PaymentStatus
from busbidder.patterns import BOOKING_REF_RE, OFFER_ID_RE


class BookingStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Booking]:
        """All saved bookings; an empty list if nothing has been booked yet."""
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DataFileError(self.path, f"cannot read bookings ({exc})") from exc
        if not isinstance(data, list):
            raise DataFileError(self.path, "expected a JSON list of bookings")

        bookings: list[Booking] = []
        for index, item in enumerate(data, start=1):
            try:
                booking = booking_from_dict(item)
            except RecordValidationError as exc:
                raise DataFileError(self.path, f"booking {index} is invalid: {exc}") from exc
            if any(b.reference == booking.reference for b in bookings):
                raise DataFileError(self.path, f"duplicate booking reference {booking.reference}")
            bookings.append(booking)
        return bookings

    def save(self, bookings: list[Booking]) -> None:
        """Write all bookings atomically: to a temporary file first, then replace the old one.

        A crash during writing therefore leaves either the old or the new file, never half of one.
        """
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps([booking_to_dict(b) for b in bookings], indent=2, ensure_ascii=False)
            temporary.write_text(text + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            raise BookingError(f"could not save bookings to {self.path}: {exc}") from exc


def booking_to_dict(booking: Booking) -> dict[str, Any]:
    return {
        "reference": booking.reference,
        "offer_id": booking.offer_id,
        "traveller_name": booking.traveller_name,
        "seats": booking.seats,
        "total_price_eur": booking.total_price_eur,
        "fare": {
            "fare_type": str(booking.fare.fare_type),
            "changeable": booking.fare.changeable,
            "refundable": booking.fare.refundable,
            "luggage_kg": booking.fare.luggage_kg,
        },
        "created_at": booking.created_at.isoformat(timespec="seconds"),
        "status": str(booking.status),
        "payment_status": str(booking.payment_status),
    }


def booking_from_dict(item: Any) -> Booking:
    """Convert one saved booking back, checking every field (raises ``RecordValidationError``)."""
    _check(isinstance(item, dict), ErrorCategory.INVALID_VALUE, "booking", "not a JSON object")
    reference = parse_text(item, "reference")
    _check(BOOKING_REF_RE.fullmatch(reference) is not None, ErrorCategory.MALFORMED_ID, "reference",
           f"reference {reference!r} does not match the pattern BB-XXXXXX")
    offer_id = parse_text(item, "offer_id")
    _check(OFFER_ID_RE.fullmatch(offer_id) is not None, ErrorCategory.MALFORMED_ID, "offer_id",
           f"offer_id {offer_id!r} is malformed")
    seats = parse_int(item, "seats")
    _check(seats >= 1, ErrorCategory.OUT_OF_RANGE, "seats", f"seats must be at least 1, got {seats}")
    total = parse_float(item, "total_price_eur")
    _check(total >= 0, ErrorCategory.OUT_OF_RANGE, "total_price_eur", f"total cannot be negative, got {total}")

    fare = item.get("fare")
    _check(isinstance(fare, dict), ErrorCategory.MISSING_FIELD, "fare", "fare conditions are missing")
    try:
        created_at = datetime.fromisoformat(parse_text(item, "created_at"))
        status = BookingStatus(parse_text(item, "status"))
        payment_status = PaymentStatus(parse_text(item, "payment_status"))
    except ValueError as exc:
        raise RecordValidationError(ErrorCategory.INVALID_VALUE, "booking", str(exc)) from None

    return Booking(
        reference=reference,
        offer_id=offer_id,
        traveller_name=parse_text(item, "traveller_name"),
        seats=seats,
        total_price_eur=total,
        fare=FareConditions(
            parse_fare_type(fare, "fare_type"),
            parse_bool(fare, "changeable"),
            parse_bool(fare, "refundable"),
            parse_int(fare, "luggage_kg"),
        ),
        created_at=created_at,
        status=status,
        payment_status=payment_status,
    )


def _check(condition: bool, category: ErrorCategory, field: str, message: str) -> None:
    if not condition:
        raise RecordValidationError(category, field, message)

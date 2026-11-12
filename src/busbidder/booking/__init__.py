"""Simulated booking: references, seat capacity and saved bookings."""

from busbidder.booking.service import BookingService, format_confirmation, new_reference
from busbidder.booking.store import BookingStore

__all__ = ["BookingService", "BookingStore", "format_confirmation", "new_reference"]

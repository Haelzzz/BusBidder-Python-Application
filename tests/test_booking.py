"""Tests for booking: references, seat capacity, saving and restoring bookings.

The ``offer`` fixture (conftest.py) has 12 seats at EUR 32.50.
"""

import dataclasses
import json
import logging
from datetime import datetime
from pathlib import Path

import pytest

from busbidder.booking import BookingService, BookingStore, format_confirmation, new_reference
from busbidder.booking.store import booking_to_dict
from busbidder.data_io.repository import MarketplaceRepository
from busbidder.exceptions import BookingError, DataFileError
from busbidder.models import BookingStatus, Offer, PaymentStatus
from busbidder.patterns import BOOKING_REF_RE

NOW = datetime(2026, 7, 1, 10, 30, 15, 123456)


def make_repository(offer: Offer) -> MarketplaceRepository:
    repository = MarketplaceRepository()
    repository.add_company(offer.company)
    repository.add_destination(offer.destination)
    repository.add_offer(offer)
    return repository


@pytest.fixture
def repository(offer: Offer) -> MarketplaceRepository:
    return make_repository(offer)


@pytest.fixture
def store(tmp_path: Path) -> BookingStore:
    return BookingStore(tmp_path / "bookings" / "bookings.json")


def make_service(repository, store, references=None) -> BookingService:
    if references is None:
        return BookingService(repository, store, clock=lambda: NOW)
    supply = iter(references)
    return BookingService(repository, store, clock=lambda: NOW, make_reference=lambda: next(supply))


# --- References ------------------------------------------------------------

def test_generated_references_match_the_pattern() -> None:
    references = {new_reference() for _ in range(200)}
    assert all(BOOKING_REF_RE.fullmatch(r) for r in references)
    assert len(references) > 190  # random, so practically never repeated
    assert not any(c in r[3:] for r in references for c in "0O1I")  # no look-alike characters


@pytest.mark.parametrize("reference", ["BB-7K2Q9", "BB-7K2Q9XX", "bb-7k2q9x", "BB-0K2Q9X", "XX-7K2Q9X", "BB7K2Q9X"])
def test_reference_pattern_rejects_malformed(reference: str) -> None:
    assert BOOKING_REF_RE.fullmatch(reference) is None


def test_duplicate_reference_is_regenerated(repository, store) -> None:
    service = make_service(repository, store, ["BB-AAAAAA", "BB-AAAAAA", "BB-BBBBBB"])
    service.book("OF-SOL-MAL-0001", "First", 1)
    assert service.book("OF-SOL-MAL-0001", "Second", 1).reference == "BB-BBBBBB"


def test_gives_up_if_no_unique_reference_can_be_made(repository, store) -> None:
    service = make_service(repository, store, ["BB-AAAAAA"] * 200)
    service.book("OF-SOL-MAL-0001", "First", 1)
    with pytest.raises(BookingError, match="unique booking reference"):
        service.book("OF-SOL-MAL-0001", "Second", 1)


# --- Booking -------------------------------------------------------------------

def test_booking_reduces_seats_and_stores_the_details(repository, store, offer: Offer) -> None:
    booking = make_service(repository, store, ["BB-AAAAAA"]).book("OF-SOL-MAL-0001", "  Ana Garcia ", 2)
    assert booking.reference == "BB-AAAAAA"
    assert booking.traveller_name == "Ana Garcia"
    assert booking.seats == 2
    assert booking.total_price_eur == 65.00
    assert booking.fare == offer.fare  # snapshot of the fare conditions sold
    assert booking.created_at == NOW.replace(microsecond=0)
    assert booking.status is BookingStatus.CONFIRMED
    assert booking.payment_status is PaymentStatus.SIMULATED_PAID
    assert offer.available_seats == 10


def test_booking_is_saved_and_can_be_read_back(repository, store) -> None:
    booking = make_service(repository, store).book("OF-SOL-MAL-0001", "Ana", 1)
    assert store.load() == [booking]
    assert not list(store.path.parent.glob("*.tmp"))  # temporary file replaced the real one


def test_last_seats_can_be_booked_then_no_more(repository, store, offer: Offer) -> None:
    service = make_service(repository, store)
    service.book("OF-SOL-MAL-0001", "Group", 12)
    assert offer.available_seats == 0
    with pytest.raises(BookingError, match="only 0 seat"):
        service.book("OF-SOL-MAL-0001", "Late", 1)


@pytest.mark.parametrize("offer_id, name, seats, message", [
    ("OF-SOL-MAL-9999", "Ana", 1, "unknown offer"),
    ("OF-SOL-MAL-0001", "   ", 1, "name is required"),
    ("OF-SOL-MAL-0001", "x" * 61, 1, "at most 60"),
    ("OF-SOL-MAL-0001", "Ana", 0, "at least 1 seat"),
    ("OF-SOL-MAL-0001", "Ana", 13, "only 12 seat"),
], ids=str)
def test_invalid_booking_changes_nothing(repository, store, offer: Offer, offer_id, name, seats, message) -> None:
    service = make_service(repository, store)
    with pytest.raises(BookingError, match=message):
        service.book(offer_id, name, seats)
    assert offer.available_seats == 12
    assert service.bookings == ()
    assert not store.path.exists()


def test_name_of_maximum_length_is_accepted(repository, store) -> None:
    assert make_service(repository, store).book("OF-SOL-MAL-0001", "x" * 60, 1)


def test_failed_save_leaves_seats_and_bookings_unchanged(repository, tmp_path: Path, offer: Offer) -> None:
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("a file where the bookings folder should be", encoding="utf-8")
    service = make_service(repository, BookingStore(blocker / "bookings.json"))
    with pytest.raises(BookingError, match="could not save"):
        service.book("OF-SOL-MAL-0001", "Ana", 2)
    assert offer.available_seats == 12
    assert service.bookings == ()


# --- Restoring saved bookings at start-up ----------------------------------------

def test_saved_bookings_reduce_seats_after_restart(repository, store, offer: Offer) -> None:
    make_service(repository, store).book("OF-SOL-MAL-0001", "Ana", 3)

    fresh = dataclasses.replace(offer, available_seats=12)  # as loaded again from offers.csv
    restarted = make_service(make_repository(fresh), store)

    assert len(restarted.bookings) == 1
    assert fresh.available_seats == 9


def test_saved_booking_for_unknown_offer_is_skipped_with_warning(
    repository, store, offer: Offer, caplog: pytest.LogCaptureFixture,
) -> None:
    make_service(repository, store).book("OF-SOL-MAL-0001", "Ana", 1)
    other = dataclasses.replace(offer, offer_id="OF-SOL-MAL-0002", available_seats=12)
    with caplog.at_level(logging.WARNING, logger="busbidder"):
        make_service(make_repository(other), store)
    assert "not in the data" in caplog.text
    assert other.available_seats == 12


def test_more_saved_seats_than_available_sets_zero(repository, store, offer: Offer, caplog) -> None:
    make_service(repository, store).book("OF-SOL-MAL-0001", "Group", 5)
    fewer = dataclasses.replace(offer, available_seats=3)  # e.g. the data was regenerated
    with caplog.at_level(logging.WARNING, logger="busbidder"):
        make_service(make_repository(fewer), store)
    assert fewer.available_seats == 0
    assert "set to 0" in caplog.text


def test_cancelled_bookings_do_not_hold_seats(repository, store, offer: Offer) -> None:
    booking = make_service(repository, store).book("OF-SOL-MAL-0001", "Ana", 4)
    booking.status = BookingStatus.CANCELLED
    store.save([booking])
    fresh = dataclasses.replace(offer, available_seats=12)
    make_service(make_repository(fresh), store)
    assert fresh.available_seats == 12


# --- Reading the bookings file -----------------------------------------------------

def test_missing_file_means_no_bookings(store) -> None:
    assert store.load() == []


@pytest.fixture
def saved(repository, store) -> dict:
    """One valid saved booking as a dict, for corrupting in the tests below."""
    return booking_to_dict(make_service(repository, store, ["BB-AAAAAA"]).book("OF-SOL-MAL-0001", "Ana", 1))


@pytest.mark.parametrize("corrupt, message", [
    (lambda b: "{not json", "cannot read bookings"),
    (lambda b: json.dumps({"reference": "BB-AAAAAA"}), "expected a JSON list"),
    (lambda b: json.dumps([b | {"reference": "BB-12345"}]), "does not match the pattern"),
    (lambda b: json.dumps([b, b]), "duplicate booking reference"),
    (lambda b: json.dumps([b | {"seats": 0}]), "seats must be at least 1"),
    (lambda b: json.dumps([{k: v for k, v in b.items() if k != "fare"}]), "fare conditions are missing"),
    (lambda b: json.dumps([b | {"status": "lost"}]), "booking 1 is invalid"),
    (lambda b: json.dumps([b | {"created_at": "yesterday"}]), "booking 1 is invalid"),
], ids=["json", "not-list", "reference", "duplicate", "seats", "fare", "status", "created_at"])
def test_corrupt_bookings_file_stops_loading(store, saved: dict, corrupt, message: str) -> None:
    store.path.write_text(corrupt(saved), encoding="utf-8")
    with pytest.raises(DataFileError, match=message):
        store.load()


def test_confirmation_contains_the_essentials(repository, store, offer: Offer) -> None:
    booking = make_service(repository, store, ["BB-AAAAAA"]).book("OF-SOL-MAL-0001", "Ana", 2)
    text = format_confirmation(booking, offer)
    assert text.startswith("Booking confirmed: BB-AAAAAA")
    assert "Madrid -> Malaga with SolRuta" in text
    assert "changeable: yes, refundable: no, luggage: 20 kg" in text
    assert "EUR 65.00 (payment simulated" in text

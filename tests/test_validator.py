"""Tests for the record validator: normal, invalid, missing-data and boundary cases."""

from datetime import datetime

import pytest

from busbidder.data_io.validator import RecordValidator
from busbidder.exceptions import ErrorCategory, RecordValidationError
from busbidder.models import Company, Destination, FareType, Offer

VALID_ROW = {
    "offer_id": "OF-SOL-MAL-0001",
    "company_id": "SOL",
    "destination_id": "MAL",
    "departure_date": "2026-07-12",
    "departure_time": "08:30",
    "arrival_date": "2026-07-12",
    "arrival_time": "14:45",
    "price_eur": "32.50",
    "transfers": "0",
    "fare_type": "standard",
    "changeable": "true",
    "refundable": "false",
    "luggage_kg": "20",
    "available_seats": "12",
    "rating": "4.1",
    "co2_kg": "15.9",
}


@pytest.fixture
def validate(company: Company, destination: Destination):
    """Validate VALID_ROW with some fields replaced (a value of None removes the field)."""
    validator = RecordValidator(rating_min=1.0, rating_max=5.0)
    companies = {company.company_id: company}
    destinations = {destination.destination_id: destination}

    def _validate(**overrides: str | None) -> Offer:
        row = VALID_ROW | overrides
        row = {key: value for key, value in row.items() if value is not None}
        return validator.offer(row, companies, destinations)

    return _validate


def assert_rejected(validate, category: ErrorCategory, field: str, **overrides: str | None) -> None:
    with pytest.raises(RecordValidationError) as info:
        validate(**overrides)
    assert info.value.category == category
    assert info.value.field == field


# --- Normal cases ---------------------------------------------------------

def test_valid_row_is_converted_to_typed_offer(validate, company: Company, destination: Destination) -> None:
    offer = validate()
    assert offer.offer_id == "OF-SOL-MAL-0001"
    assert offer.company is company
    assert offer.destination is destination
    assert offer.departure == datetime(2026, 7, 12, 8, 30)
    assert offer.arrival == datetime(2026, 7, 12, 14, 45)
    assert offer.price_eur == 32.5
    assert offer.transfers == 0
    assert offer.fare.fare_type is FareType.STANDARD
    assert offer.fare.changeable is True
    assert offer.fare.refundable is False
    assert offer.fare.luggage_kg == 20
    assert offer.available_seats == 12
    assert offer.rating == 4.1
    assert offer.co2_kg == 15.9


def test_overnight_offer_is_valid(validate) -> None:
    offer = validate(departure_time="23:30", arrival_date="2026-07-13", arrival_time="06:15")
    assert offer.is_overnight
    assert offer.duration_min == 405


def test_harmless_formatting_is_normalised(validate) -> None:
    offer = validate(price_eur=" 32.50 ", changeable="YES", refundable="False", fare_type="Flex")
    assert offer.price_eur == 32.5
    assert offer.fare.changeable is True
    assert offer.fare.refundable is False
    assert offer.fare.fare_type is FareType.FLEX


# --- Missing data ---------------------------------------------------------

@pytest.mark.parametrize("co2", ["", "  ", None])
def test_optional_co2_may_be_missing(validate, co2: str | None) -> None:
    assert validate(co2_kg=co2).co2_kg is None


@pytest.mark.parametrize("field", ["offer_id", "price_eur", "departure_time", "arrival_date", "rating"])
@pytest.mark.parametrize("value", ["", "   ", None], ids=["empty", "blank", "absent"])
def test_missing_required_field_is_rejected(validate, field: str, value: str | None) -> None:
    assert_rejected(validate, ErrorCategory.MISSING_FIELD, field, **{field: value})


# --- Boundary cases -------------------------------------------------------

@pytest.mark.parametrize("overrides", [
    {"rating": "1.0"},
    {"rating": "5.0"},
    {"available_seats": "1"},
    {"price_eur": "0.01"},
    {"transfers": "0"},
    {"luggage_kg": "0"},
    {"departure_time": "00:00"},
    {"departure_time": "13:00", "arrival_time": "23:59"},
    {"departure_time": "14:44"},  # one minute before arrival
], ids=str)
def test_boundary_values_are_accepted(validate, overrides: dict[str, str]) -> None:
    validate(**overrides)


@pytest.mark.parametrize("overrides, category, field", [
    ({"rating": "0.9"}, ErrorCategory.OUT_OF_RANGE, "rating"),
    ({"rating": "5.1"}, ErrorCategory.OUT_OF_RANGE, "rating"),
    ({"available_seats": "0"}, ErrorCategory.NO_AVAILABILITY, "available_seats"),
    ({"available_seats": "-1"}, ErrorCategory.OUT_OF_RANGE, "available_seats"),
    ({"price_eur": "0"}, ErrorCategory.OUT_OF_RANGE, "price_eur"),
    ({"transfers": "-1"}, ErrorCategory.OUT_OF_RANGE, "transfers"),
    ({"departure_time": "24:00"}, ErrorCategory.INVALID_DATETIME, "departure_time"),
    ({"departure_time": "14:45"}, ErrorCategory.INCONSISTENT, "arrival_time"),  # arrival == departure
], ids=str)
def test_values_just_outside_limits_are_rejected(validate, overrides, category, field) -> None:
    assert_rejected(validate, category, field, **overrides)


def test_rating_scale_comes_from_settings(company: Company, destination: Destination) -> None:
    validator = RecordValidator(rating_min=0.0, rating_max=10.0)
    offer = validator.offer(VALID_ROW | {"rating": "6.5"}, {"SOL": company}, {"MAL": destination})
    assert offer.rating == 6.5


# --- Invalid cases --------------------------------------------------------

@pytest.mark.parametrize("overrides, category, field", [
    ({"price_eur": "-12.50"}, ErrorCategory.OUT_OF_RANGE, "price_eur"),
    ({"price_eur": "abc"}, ErrorCategory.INVALID_VALUE, "price_eur"),
    ({"price_eur": "nan"}, ErrorCategory.INVALID_VALUE, "price_eur"),
    ({"rating": "6.5"}, ErrorCategory.OUT_OF_RANGE, "rating"),
    ({"available_seats": "2.5"}, ErrorCategory.INVALID_VALUE, "available_seats"),
    ({"co2_kg": "-1"}, ErrorCategory.OUT_OF_RANGE, "co2_kg"),
    ({"fare_type": "premium"}, ErrorCategory.INVALID_VALUE, "fare_type"),
    ({"changeable": "maybe"}, ErrorCategory.INVALID_VALUE, "changeable"),
    ({"departure_date": "2026-06-31"}, ErrorCategory.INVALID_DATETIME, "departure_date"),
    ({"departure_date": "14/07/2026"}, ErrorCategory.INVALID_DATETIME, "departure_date"),
    ({"departure_time": "25:10"}, ErrorCategory.INVALID_DATETIME, "departure_time"),
    ({"departure_time": "8:30"}, ErrorCategory.INVALID_DATETIME, "departure_time"),
    ({"departure_time": "08:60"}, ErrorCategory.INVALID_DATETIME, "departure_time"),
    ({"arrival_time": "07:00"}, ErrorCategory.INCONSISTENT, "arrival_time"),
    ({"offer_id": "OF-SOL-XYZ-0001", "destination_id": "XYZ"}, ErrorCategory.UNKNOWN_REFERENCE, "destination_id"),
    ({"offer_id": "OF-CAM-MAL-0001", "company_id": "CAM"}, ErrorCategory.UNKNOWN_REFERENCE, "company_id"),
    ({"offer_id": "OF-SOL-MAL-12A"}, ErrorCategory.MALFORMED_ID, "offer_id"),
    ({"offer_id": "of_sol_mal_0001"}, ErrorCategory.MALFORMED_ID, "offer_id"),
    ({"offer_id": "OF-SOL-MAL-00001"}, ErrorCategory.MALFORMED_ID, "offer_id"),
    ({"company_id": "sol"}, ErrorCategory.MALFORMED_ID, "company_id"),
    ({"offer_id": "OF-NOC-MAL-0001"}, ErrorCategory.INCONSISTENT, "offer_id"),  # ID says NOC, column says SOL
], ids=str)
def test_invalid_values_are_rejected_with_category(validate, overrides, category, field) -> None:
    assert_rejected(validate, category, field, **overrides)


def test_row_with_extra_values_is_rejected(company: Company, destination: Destination) -> None:
    row = VALID_ROW | {None: ["surplus"]}  # how csv.DictReader stores values beyond the header
    with pytest.raises(RecordValidationError) as info:
        RecordValidator().offer(row, {"SOL": company}, {"MAL": destination})
    assert info.value.category == ErrorCategory.INVALID_VALUE


# --- Companies and destinations (native JSON values) ------------------------

def test_valid_company_and_destination() -> None:
    validator = RecordValidator()
    company = validator.company({"company_id": "SOL", "name": "SolRuta", "profile": "Low-cost"})
    destination = validator.destination({
        "destination_id": "MAL", "name": "Malaga", "region": "Andalusia",
        "coastal": True, "distance_km": 530, "base_duration_min": 360,
    })
    assert company == Company("SOL", "SolRuta", "Low-cost")
    assert destination == Destination("MAL", "Malaga", "Andalusia", True, 530, 360)


@pytest.mark.parametrize("overrides, category, field", [
    ({"name": None}, ErrorCategory.MISSING_FIELD, "name"),
    ({"destination_id": "Mal"}, ErrorCategory.MALFORMED_ID, "destination_id"),
    ({"coastal": "maybe"}, ErrorCategory.INVALID_VALUE, "coastal"),
    ({"distance_km": 0}, ErrorCategory.OUT_OF_RANGE, "distance_km"),
    ({"distance_km": True}, ErrorCategory.INVALID_VALUE, "distance_km"),  # bool is not a number here
    ({"base_duration_min": -60}, ErrorCategory.OUT_OF_RANGE, "base_duration_min"),
], ids=str)
def test_invalid_destination_is_rejected(overrides, category, field) -> None:
    raw = {"destination_id": "MAL", "name": "Malaga", "region": "Andalusia",
           "coastal": True, "distance_km": 530, "base_duration_min": 360} | overrides
    raw = {key: value for key, value in raw.items() if value is not None}
    with pytest.raises(RecordValidationError) as info:
        RecordValidator().destination(raw)
    assert (info.value.category, info.value.field) == (category, field)

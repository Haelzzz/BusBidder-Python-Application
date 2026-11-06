"""Converts raw records into domain objects, or rejects them with a category.

Each ``RecordValidator`` method either returns a valid model object or raises
``RecordValidationError`` at the first problem found (fail-fast), so every
rejected record has exactly one category in the load summary.

Values are converted here rather than in the loader, because a value that
cannot be converted (e.g. "abc" as a price) is itself a validation result.

Invalid values are never corrected: guessing what a supplier meant by a
negative price or an impossible date could show a traveller wrong information.
The only normalisation is harmless formatting: surrounding whitespace is
stripped and booleans accept true/false, yes/no and 1/0 in any letter case.
"""

import math
from collections.abc import Mapping
from datetime import date, datetime, time
from typing import Any

from busbidder.exceptions import ErrorCategory, RecordValidationError
from busbidder.models import Company, Destination, FareConditions, FareType, Offer
from busbidder.patterns import CODE_RE, OFFER_ID_RE, TIME_RE

_TRUE = {"true", "yes", "1"}
_FALSE = {"false", "no", "0"}

Raw = Mapping[Any, Any]


class RecordValidator:
    """Validates company, destination and offer records.

    Holds the rating scale from the settings, which is why it is a class
    rather than a set of free functions.
    """

    def __init__(self, rating_min: float = 1.0, rating_max: float = 5.0) -> None:
        self.rating_min = rating_min
        self.rating_max = rating_max

    def company(self, raw: Raw) -> Company:
        return Company(
            company_id=parse_code(raw, "company_id"),
            name=parse_text(raw, "name"),
            profile=parse_text(raw, "profile"),
        )

    def destination(self, raw: Raw) -> Destination:
        destination_id = parse_code(raw, "destination_id")
        name = parse_text(raw, "name")
        region = parse_text(raw, "region")
        coastal = parse_bool(raw, "coastal")
        distance_km = parse_int(raw, "distance_km")
        base_duration_min = parse_int(raw, "base_duration_min")
        _require(distance_km > 0, ErrorCategory.OUT_OF_RANGE, "distance_km",
                 f"distance_km must be positive, got {distance_km}")
        _require(base_duration_min > 0, ErrorCategory.OUT_OF_RANGE, "base_duration_min",
                 f"base_duration_min must be positive, got {base_duration_min}")
        return Destination(destination_id, name, region, coastal, distance_km, base_duration_min)

    def offer(
        self,
        raw: Raw,
        companies: Mapping[str, Company],
        destinations: Mapping[str, Destination],
    ) -> Offer:
        """Validate one offer row against the already loaded companies and destinations.

        Order of checks: row shape, identifiers, references, value types,
        value ranges, cross-field consistency, availability.
        """

        _require(None not in raw, ErrorCategory.INVALID_VALUE, "row",
                 "row has more values than the header has columns")

        offer_id = parse_text(raw, "offer_id")
        id_match = OFFER_ID_RE.fullmatch(offer_id)
        _require(id_match is not None, ErrorCategory.MALFORMED_ID, "offer_id",
                 f"offer_id {offer_id!r} does not match the pattern OF-XXX-YYY-0000")
        company_id = parse_code(raw, "company_id")
        destination_id = parse_code(raw, "destination_id")
        _require(id_match["company"] == company_id and id_match["destination"] == destination_id,
                 ErrorCategory.INCONSISTENT, "offer_id",
                 f"offer_id {offer_id!r} does not match company {company_id} and destination {destination_id}")

        _require(company_id in companies, ErrorCategory.UNKNOWN_REFERENCE, "company_id",
                 f"unknown company {company_id!r}")
        _require(destination_id in destinations, ErrorCategory.UNKNOWN_REFERENCE, "destination_id",
                 f"unknown destination {destination_id!r}")

        departure = datetime.combine(parse_date(raw, "departure_date"), parse_time(raw, "departure_time"))
        arrival = datetime.combine(parse_date(raw, "arrival_date"), parse_time(raw, "arrival_time"))
        price = parse_float(raw, "price_eur")
        transfers = parse_int(raw, "transfers")
        fare_type = parse_fare_type(raw, "fare_type")
        changeable = parse_bool(raw, "changeable")
        refundable = parse_bool(raw, "refundable")
        luggage_kg = parse_int(raw, "luggage_kg")
        seats = parse_int(raw, "available_seats")
        rating = parse_float(raw, "rating")
        co2 = None if is_blank(raw.get("co2_kg")) else parse_float(raw, "co2_kg")  # optional field

        _require(price > 0, ErrorCategory.OUT_OF_RANGE, "price_eur", f"price_eur must be positive, got {price}")
        _require(transfers >= 0, ErrorCategory.OUT_OF_RANGE, "transfers",
                 f"transfers cannot be negative, got {transfers}")
        _require(luggage_kg >= 0, ErrorCategory.OUT_OF_RANGE, "luggage_kg",
                 f"luggage_kg cannot be negative, got {luggage_kg}")
        _require(seats >= 0, ErrorCategory.OUT_OF_RANGE, "available_seats",
                 f"available_seats cannot be negative, got {seats}")
        _require(self.rating_min <= rating <= self.rating_max, ErrorCategory.OUT_OF_RANGE, "rating",
                 f"rating {rating} is outside the scale {self.rating_min}-{self.rating_max}")
        _require(co2 is None or co2 >= 0, ErrorCategory.OUT_OF_RANGE, "co2_kg",
                 f"co2_kg cannot be negative, got {co2}")
        _require(arrival > departure, ErrorCategory.INCONSISTENT, "arrival_time",
                 f"arrival {arrival:%Y-%m-%d %H:%M} is not after departure {departure:%Y-%m-%d %H:%M}")
        _require(seats > 0, ErrorCategory.NO_AVAILABILITY, "available_seats", "no seats available")

        return Offer(
            offer_id=offer_id,
            company=companies[company_id],
            destination=destinations[destination_id],
            departure=departure,
            arrival=arrival,
            price_eur=price,
            transfers=transfers,
            available_seats=seats,
            rating=rating,
            fare=FareConditions(fare_type, changeable, refundable, luggage_kg),
            co2_kg=co2,
        )



def _require(condition: bool, category: ErrorCategory, field: str, message: str) -> None:
    if not condition:
        raise RecordValidationError(category, field, message)


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def required(raw: Raw, field: str) -> Any:
    """Return the field's value (stripped if text), or raise MISSING_FIELD."""
    value = raw.get(field)
    _require(not is_blank(value), ErrorCategory.MISSING_FIELD, field, f"{field} is missing")
    return value.strip() if isinstance(value, str) else value


def parse_text(raw: Raw, field: str) -> str:
    value = required(raw, field)
    _require(isinstance(value, str), ErrorCategory.INVALID_VALUE, field, f"{field} must be text, got {value!r}")
    return value

def parse_code(raw: Raw, field: str) -> str:
    value = parse_text(raw, field)
    _require(CODE_RE.fullmatch(value) is not None, ErrorCategory.MALFORMED_ID, field,
             f"{field} {value!r} must be three capital letters")
    return value


def parse_int(raw: Raw, field: str) -> int:
    value = required(raw, field)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    raise RecordValidationError(ErrorCategory.INVALID_VALUE, field, f"{field} must be a whole number, got {value!r}")

def parse_float(raw: Raw, field: str) -> float:
    value = required(raw, field)
    number: float | None = None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            pass

    _require(number is not None and math.isfinite(number), ErrorCategory.INVALID_VALUE, field,
             f"{field} must be a number, got {value!r}")
    return number  


def parse_bool(raw: Raw, field: str) -> bool:
    value = required(raw, field)
    if isinstance(value, bool):
        return value
    text = str(value).lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise RecordValidationError(ErrorCategory.INVALID_VALUE, field, f"{field} must be true or false, got {value!r}")


def parse_fare_type(raw: Raw, field: str) -> FareType:
    value = parse_text(raw, field)
    try:
        return FareType(value.lower())
    except ValueError:
        known = ", ".join(fare.value for fare in FareType)
        raise RecordValidationError(ErrorCategory.INVALID_VALUE, field,
                                    f"{field} {value!r} is not one of: {known}") from None


def parse_date(raw: Raw, field: str) -> date:
    value = parse_text(raw, field)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise RecordValidationError(ErrorCategory.INVALID_DATETIME, field,
                                    f"{field} {value!r} is not a valid date (YYYY-MM-DD)") from None


def parse_time(raw: Raw, field: str) -> time:
    value = parse_text(raw, field)
    match = TIME_RE.fullmatch(value)
    _require(match is not None, ErrorCategory.INVALID_DATETIME, field,
             f"{field} {value!r} is not a valid time (HH:MM, 00:00-23:59)")
    return time(int(match["hour"]), int(match["minute"]))

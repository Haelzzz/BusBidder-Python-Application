"""Shared test fixtures."""

from datetime import datetime
from pathlib import Path

import pytest

from busbidder.models import Company, Destination, FareConditions, FareType, Offer
from busbidder.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_settings(tmp_path: Path) -> Settings:
    """Settings pointing at the small fixture files; outputs go to a temporary folder."""
    return Settings(
        origin="Madrid",
        companies_file=FIXTURES / "companies.json",
        destinations_file=FIXTURES / "destinations.json",
        offers_file=FIXTURES / "offers.csv",
        review_file=tmp_path / "rejected_records.csv",
        bookings_file=tmp_path / "bookings.json",
        log_file=tmp_path / "busbidder.log",
        log_level="INFO",
        rating_min=1.0,
        rating_max=5.0,
    )


@pytest.fixture
def company() -> Company:
    return Company("SOL", "SolRuta", "Low-cost daytime services")


@pytest.fixture
def destination() -> Destination:
    return Destination("MAL", "Malaga", "Andalusia", True, 530, 360)


@pytest.fixture
def fare() -> FareConditions:
    return FareConditions(FareType.STANDARD, changeable=True, refundable=False, luggage_kg=20)


@pytest.fixture
def offer(company: Company, destination: Destination, fare: FareConditions) -> Offer:
    return Offer(
        offer_id="OF-SOL-MAL-0001",
        company=company,
        destination=destination,
        departure=datetime(2026, 7, 12, 8, 30),
        arrival=datetime(2026, 7, 12, 14, 45),
        price_eur=32.5,
        transfers=0,
        available_seats=12,
        rating=4.1,
        fare=fare,
    )

"""Tests for reading files and loading the marketplace.

The fixture files in tests/fixtures/ contain:

- companies.json: SOL and NOC valid; a malformed ID and a duplicate SOL.
- destinations.json: MAL and TOL valid; ZAR with a negative distance.
- offers.csv: three valid offers using boundary values (00:00 and 23:59
  departures, overnight arrival, 1 seat, ratings 1.0 and 5.0, mixed-case
  booleans, empty CO2), then a negative price, an offer to ZAR (rejected
  above, so unknown), time 24:00, a duplicate ID and a missing price.
"""

import csv
import dataclasses
import json
import logging
from pathlib import Path

import pytest

from busbidder.data_io.loader import OFFER_COLUMNS, load_marketplace, read_csv_records, read_json_records
from busbidder.exceptions import DataFileError, ErrorCategory
from busbidder.settings import Settings, load_settings

PROJECT_DATA = Path(__file__).resolve().parents[1] / "data"


# --- File-level errors ----------------------------------------------------

def test_missing_json_file(tmp_path: Path) -> None:
    with pytest.raises(DataFileError, match="file not found"):
        read_json_records(tmp_path / "nope.json")


@pytest.mark.parametrize("content, message", [
    ('[{"company_id": "SOL",}]', "invalid JSON"),
    ('{"company_id": "SOL"}', "expected a JSON list"),
    ('[{"company_id": "SOL"}, "SOL"]', "record 2 is not a JSON object"),
])
def test_malformed_json_file(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "companies.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DataFileError, match=message):
        read_json_records(path)


def test_missing_csv_file(tmp_path: Path) -> None:
    with pytest.raises(DataFileError, match="file not found"):
        read_csv_records(tmp_path / "nope.csv", OFFER_COLUMNS)


def test_empty_csv_file(tmp_path: Path) -> None:
    path = tmp_path / "offers.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DataFileError, match="empty"):
        read_csv_records(path, OFFER_COLUMNS)


def test_csv_missing_required_column(tmp_path: Path) -> None:
    path = tmp_path / "offers.csv"
    path.write_text(",".join(c for c in OFFER_COLUMNS if c != "price_eur") + "\n", encoding="utf-8")
    with pytest.raises(DataFileError, match="missing columns: price_eur"):
        read_csv_records(path, OFFER_COLUMNS)


def test_csv_without_optional_co2_column_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "offers.csv"
    path.write_text(",".join(OFFER_COLUMNS) + "\n", encoding="utf-8")
    assert read_csv_records(path, OFFER_COLUMNS) == []


def test_csv_records_keep_line_numbers() -> None:
    records = read_csv_records(Path(__file__).parent / "fixtures" / "offers.csv", OFFER_COLUMNS)
    assert [r.position for r in records[:2]] == [2, 3]  # line 1 is the header


def test_no_valid_companies_stops_loading(fixture_settings: Settings, tmp_path: Path) -> None:
    empty = tmp_path / "companies.json"
    empty.write_text("[]", encoding="utf-8")
    with pytest.raises(DataFileError, match="no valid companies"):
        load_marketplace(dataclasses.replace(fixture_settings, companies_file=empty))


# --- Loading the fixture data ---------------------------------------------

def test_load_counts_per_file(fixture_settings: Settings) -> None:
    _, report = load_marketplace(fixture_settings)
    assert report.loaded == {"companies.json": 2, "destinations.json": 2, "offers.csv": 3}
    assert report.rejected_from("companies.json") == 2
    assert report.rejected_from("destinations.json") == 1
    assert report.rejected_from("offers.csv") == 5


def test_rejections_by_record_and_category(fixture_settings: Settings) -> None:
    _, report = load_marketplace(fixture_settings)
    found = {(r.source, r.position, r.category) for r in report.rejected}
    assert found == {
        ("companies.json", 3, ErrorCategory.MALFORMED_ID),
        ("companies.json", 4, ErrorCategory.DUPLICATE_ID),
        ("destinations.json", 3, ErrorCategory.OUT_OF_RANGE),
        ("offers.csv", 5, ErrorCategory.OUT_OF_RANGE),
        ("offers.csv", 6, ErrorCategory.UNKNOWN_REFERENCE),
        ("offers.csv", 7, ErrorCategory.INVALID_DATETIME),
        ("offers.csv", 8, ErrorCategory.DUPLICATE_ID),
        ("offers.csv", 9, ErrorCategory.MISSING_FIELD),
    }


def test_first_of_duplicate_ids_is_kept(fixture_settings: Settings) -> None:
    repository, _ = load_marketplace(fixture_settings)
    assert repository.companies["SOL"].name == "SolRuta"
    assert repository.find_offer("OF-SOL-MAL-0001").departure.day == 12


def test_repository_contains_typed_offers(fixture_settings: Settings) -> None:
    repository, _ = load_marketplace(fixture_settings)
    assert [o.offer_id for o in repository.offers_to("MAL")] == ["OF-SOL-MAL-0001", "OF-NOC-MAL-0001"]
    overnight = repository.find_offer("OF-NOC-MAL-0001")
    assert overnight.is_overnight and overnight.fare.refundable is True
    assert repository.find_offer("OF-SOL-TOL-0001").co2_kg is None
    assert repository.find_offer("missing") is None


def test_review_file_lists_rejected_records(fixture_settings: Settings) -> None:
    _, report = load_marketplace(fixture_settings)
    with fixture_settings.review_file.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(report.rejected) == 8
    negative = next(row for row in rows if row["record_id"] == "OF-SOL-MAL-0002")
    assert negative["category"] == "out_of_range"
    assert json.loads(negative["raw_record"])["price_eur"] == "-1.00"  # original value kept for review


def test_review_file_is_replaced_not_appended(fixture_settings: Settings) -> None:
    fixture_settings.review_file.write_text("stale content from an earlier run\n", encoding="utf-8")
    load_marketplace(fixture_settings)
    text = fixture_settings.review_file.read_text(encoding="utf-8")
    assert "stale content" not in text
    assert text.startswith("source,position,record_id")


def test_rejections_are_logged_as_warnings(fixture_settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="busbidder"):
        load_marketplace(fixture_settings)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 8
    assert any("OF-SOL-MAL-0002" in r.getMessage() for r in warnings)


def test_summary_mentions_counts_and_categories(fixture_settings: Settings) -> None:
    _, report = load_marketplace(fixture_settings)
    summary = report.summary()
    assert "offers.csv" in summary and "3 loaded" in summary
    assert "duplicate_id" in summary


# --- The real dataset -----------------------------------------------------

# How the generator's problem labels map onto the validator's categories.
EXPECTED_CATEGORY = {
    "negative_price": ErrorCategory.OUT_OF_RANGE,
    "unknown_destination": ErrorCategory.UNKNOWN_REFERENCE,
    "invalid_date": ErrorCategory.INVALID_DATETIME,
    "invalid_time": ErrorCategory.INVALID_DATETIME,
    "arrival_before_departure": ErrorCategory.INCONSISTENT,
    "rating_out_of_scale": ErrorCategory.OUT_OF_RANGE,
    "zero_seats": ErrorCategory.NO_AVAILABILITY,
    "missing_field": ErrorCategory.MISSING_FIELD,
    "malformed_id": ErrorCategory.MALFORMED_ID,
}


def test_real_dataset_rejects_exactly_the_injected_records(tmp_path: Path) -> None:
    settings = dataclasses.replace(load_settings(), review_file=tmp_path / "rejected.csv")
    manifest = json.loads((PROJECT_DATA / "injected_errors.json").read_text(encoding="utf-8"))

    repository, report = load_marketplace(settings)

    expected = {(e["offer_id"], EXPECTED_CATEGORY[e["problem"]]) for e in manifest["injected"]}
    assert {(r.record_id, r.category) for r in report.rejected} == expected
    assert len(repository.offers) == manifest["valid_offers"]

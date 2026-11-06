"""Reads the data files and builds the marketplace.

Invalid data is handled at two levels:

- File level (file missing or unreadable, invalid JSON, missing CSV columns,
  no valid companies or destinations): ``DataFileError`` is raised and loading
  stops, because nothing meaningful can be built from a broken file.
- Record level (one bad row): the record is rejected, logged, and written to a
  review file with its category and original values; loading continues.
"""

import csv
import json
import logging
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from busbidder.data_io.repository import MarketplaceRepository
from busbidder.data_io.validator import RecordValidator
from busbidder.exceptions import DataFileError, ErrorCategory, RecordValidationError
from busbidder.settings import Settings

logger = logging.getLogger(__name__)

# co2_kg is not required: the environmental measure is optional.
OFFER_COLUMNS = (
    "offer_id", "company_id", "destination_id",
    "departure_date", "departure_time", "arrival_date", "arrival_time",
    "price_eur", "transfers", "fare_type", "changeable", "refundable", "luggage_kg",
    "available_seats", "rating",
)
REVIEW_COLUMNS = ("source", "position", "record_id", "category", "field", "message", "raw_record")


@dataclass(frozen=True, slots=True)
class RawRecord:
    """One record as read from a file, before any conversion."""

    source: str  
    position: int  
    data: Mapping[Any, Any]


@dataclass(frozen=True, slots=True)
class Rejection:
    """A record that failed validation, with the reason."""

    source: str
    position: int
    record_id: str
    category: ErrorCategory
    field: str
    message: str
    raw: Mapping[Any, Any]


@dataclass
class LoadReport:
    """What happened during loading: counts per file and every rejection."""

    loaded: dict[str, int] = field(default_factory=dict) 
    rejected: list[Rejection] = field(default_factory=list)

    def rejected_from(self, source: str) -> int:
        return sum(1 for rejection in self.rejected if rejection.source == source)

    def by_category(self) -> Counter[ErrorCategory]:
        return Counter(rejection.category for rejection in self.rejected)

    def summary(self) -> str:
        lines = ["Data loaded:"]
        for source, count in self.loaded.items():
            lines.append(f"  {source:<20}{count:>6} loaded{self.rejected_from(source):>6} rejected")
        if self.rejected:
            lines.append("Rejected by category:")
            for category, count in sorted(self.by_category().items()):
                lines.append(f"  {category:<20}{count:>6}")
        return "\n".join(lines)


def read_json_records(path: Path) -> list[RawRecord]:
    """Read a JSON file containing a list of objects."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise DataFileError(path, "file not found") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise DataFileError(path, f"cannot read file ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise DataFileError(path, f"invalid JSON at line {exc.lineno}: {exc.msg}") from exc

    if not isinstance(data, list):
        raise DataFileError(path, "expected a JSON list of records")
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise DataFileError(path, f"record {index} is not a JSON object")
    return [RawRecord(path.name, index, item) for index, item in enumerate(data, start=1)]


def read_csv_records(path: Path, required_columns: Iterable[str]) -> list[RawRecord]:
    """Read a CSV file with a header row, checking that the required columns exist."""
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise DataFileError(path, "file is empty")
            missing = [column for column in required_columns if column not in reader.fieldnames]
            if missing:
                raise DataFileError(path, f"missing columns: {', '.join(missing)}")
            return [RawRecord(path.name, reader.line_num, row) for row in reader]
    except FileNotFoundError:
        raise DataFileError(path, "file not found") from None
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise DataFileError(path, f"cannot read file ({exc})") from exc


def load_marketplace(settings: Settings) -> tuple[MarketplaceRepository, LoadReport]:
    """Read, validate and store all data files; write rejected records to the review file."""
    validator = RecordValidator(settings.rating_min, settings.rating_max)
    repository = MarketplaceRepository()
    report = LoadReport()

    _load_records(
        settings.companies_file, read_json_records(settings.companies_file), "company_id", report,
        lambda raw: repository.add_company(validator.company(raw)),
    )
    _load_records(
        settings.destinations_file, read_json_records(settings.destinations_file), "destination_id", report,
        lambda raw: repository.add_destination(validator.destination(raw)),
    )
   
    if not repository.companies:
        raise DataFileError(settings.companies_file, "no valid companies")
    if not repository.destinations:
        raise DataFileError(settings.destinations_file, "no valid destinations")

    _load_records(
        settings.offers_file, read_csv_records(settings.offers_file, OFFER_COLUMNS), "offer_id", report,
        lambda raw: repository.add_offer(validator.offer(raw, repository.companies, repository.destinations)),
    )

    write_review_file(settings.review_file, report.rejected)
    logger.info("Loading finished: %d records loaded, %d rejected",
                sum(report.loaded.values()), len(report.rejected))
    return repository, report


def _load_records(
    path: Path,
    records: list[RawRecord],
    id_field: str,
    report: LoadReport,
    add: Callable[[Mapping[Any, Any]], None],
) -> None:
    """Validate and add each record, collecting rejections in the report."""
    logger.info("Read %d records from %s", len(records), path)
    loaded = 0
    for record in records:
        try:
            add(record.data)
        except RecordValidationError as exc:
            record_id = str(record.data.get(id_field) or "")
            report.rejected.append(Rejection(
                record.source, record.position, record_id, exc.category, exc.field, str(exc), record.data,
            ))
            logger.warning("Rejected %s position %d (%s): %s: %s",
                           record.source, record.position, record_id or "no id", exc.category, exc)
        else:
            loaded += 1
    report.loaded[path.name] = loaded


def write_review_file(path: Path, rejections: list[Rejection]) -> None:
    """Write rejected records for manual review. Rewritten on every load, so it is never stale."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(REVIEW_COLUMNS)
            for r in rejections:
                raw = json.dumps({str(k): v for k, v in r.raw.items()}, ensure_ascii=False)
                writer.writerow([r.source, r.position, r.record_id, r.category, r.field, r.message, raw])
    except OSError as exc:
        logger.error("Could not write review file %s: %s", path, exc)
        return
    logger.info("Wrote %d rejected records to %s", len(rejections), path)

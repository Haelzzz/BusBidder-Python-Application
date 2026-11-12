"""Command-line interface.

For now it loads and validates the data, prints the load summary, and filters
and ranks the offers for the example traveller from the project specification.
The interactive part (choose profile, book) is built in a later task.
"""

import sys
from datetime import date, time
from pathlib import Path

from busbidder.data_io.loader import load_marketplace
from busbidder.exceptions import BusBidderError, ConfigError
from busbidder.filtering import FilterResult, filter_offers
from busbidder.logging_setup import setup_logging
from busbidder.models import TravellerRequest
from busbidder.paths import PROJECT_ROOT
from busbidder.ranking import rank_offers
from busbidder.settings import load_settings

EXAMPLE_REQUEST = TravellerRequest(
    destination_id="MAL",
    earliest_date=date(2026, 7, 12),
    latest_date=date(2026, 7, 14),
    max_budget_eur=50.0,
    preferred_departure=time(9, 0),
    max_transfers=1,
    require_changeable=True,
    weights={"price": 0.40, "duration": 0.25, "departure": 0.15, "flexibility": 0.20},
)


def main(argv: list[str] | None = None) -> int:
    """Run the application and return a process exit code."""
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    logger = setup_logging(settings.log_file, settings.log_level)
    logger.info("BusBidder started")
    try:
        repository, report = load_marketplace(settings)
    except BusBidderError as exc:
        logger.error("Loading failed: %s", exc)
        return 1

    print(report.summary())
    if report.rejected:
        print(f"Rejected records written to {_display(settings.review_file)} "
              f"(details in {_display(settings.log_file)})")

    request = EXAMPLE_REQUEST
    destination = repository.destinations[request.destination_id]
    print(f"\nExample request: Madrid to {destination.name}")
    result = filter_offers(repository.offers_to(request.destination_id), request)
    print(result.summary())
    _print_removed(result)
    try:
        ranking = rank_offers(result.accepted, request)
    except BusBidderError as exc:
        logger.error("Ranking failed: %s", exc)
        return 1
    print("\nRanked acceptable offers (raw value and score 0-100 per criterion):")
    print(ranking.table())
    print("\nBooking is not implemented yet.")
    return 0


def _print_removed(result: FilterResult, max_removed: int = 5) -> None:
    """List some offers inside the travel window that were removed, with reasons."""
    in_window = [r for r in result.rejected if all(v.constraint != "travel_window" for v in r.violations)]
    if in_window:
        print(f"\nRemoved offers inside the travel window (first {min(max_removed, len(in_window))} "
              f"of {len(in_window)}):")
        for rejected in sorted(in_window, key=lambda r: r.offer.departure)[:max_removed]:
            print(f"  {rejected.offer.offer_id}  {rejected.explain()}")


def _display(path: Path) -> str:
    """Show paths inside the project relative to it, for shorter output."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)

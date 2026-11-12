"""Command-line interface.

For now it loads and validates the data, then runs every traveller profile on
the trip from the project specification and compares the recommendations. The
interactive part (choose profile and trip, book) is built in a later task.
"""

import sys
from datetime import date
from pathlib import Path

from busbidder.data_io.loader import load_marketplace
from busbidder.data_io.profiles import load_profiles
from busbidder.exceptions import BusBidderError, ConfigError
from busbidder.filtering import filter_offers
from busbidder.logging_setup import setup_logging
from busbidder.models import Trip
from busbidder.paths import PROJECT_ROOT
from busbidder.ranking import RankedOffer, explain_top, rank_offers
from busbidder.settings import load_settings

# The trip from the specification. Temporary: chosen by the user in a later task.
EXAMPLE_TRIP = Trip("MAL", date(2026, 7, 12), date(2026, 7, 14), max_budget_eur=50.0)
TOP_ROWS = 5


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
        profiles = load_profiles()
    except BusBidderError as exc:
        logger.error("Start-up failed: %s", exc)
        return 1

    print(report.summary())
    if report.rejected:
        print(f"Rejected records written to {_display(settings.review_file)} "
              f"(details in {_display(settings.log_file)})")

    trip = EXAMPLE_TRIP
    destination = repository.destinations[trip.destination_id]
    print(f"\nExample trip: Madrid to {destination.name}, {trip.earliest_date} to {trip.latest_date}, "
          f"budget EUR {trip.max_budget_eur:.2f}. Compared across {len(profiles)} traveller profiles.")

    recommendations: list[tuple[str, int, RankedOffer | None]] = []
    for profile in profiles.values():
        request = profile.request_for(trip)
        result = filter_offers(repository.offers_to(trip.destination_id), request)
        try:
            ranking = rank_offers(result.accepted, request)
        except BusBidderError as exc:
            logger.error("Ranking failed for profile %s: %s", profile.key, exc)
            return 1

        print(f"\n{'=' * 100}\n{profile.name}: {profile.description}\n")
        print(result.summary())
        if ranking.offers:
            print(f"\nTop {min(TOP_ROWS, len(ranking.offers))} of {len(ranking.offers)} "
                  "(raw value and score 0-100 per criterion):")
            print(ranking.table(limit=TOP_ROWS))
            print()
            print(explain_top(ranking).text())
        recommendations.append((profile.name, len(result.accepted), ranking.top))

    print(f"\n{'=' * 100}\nRecommendation per profile (same trip, same offers):")
    print(f"  {'Profile':<45}{'Acceptable':>10}  Recommended offer")
    for name, acceptable, top in recommendations:
        offer = (f"{top.offer.offer_id}  {top.offer.company.name:<16}{top.offer.departure:%d %b %H:%M}  "
                 f"EUR {top.offer.price_eur:>6.2f}  score {top.total:.1f}") if top else "none"
        print(f"  {name:<45}{acceptable:>10}  {offer}")
    print("\nBooking is not implemented yet.")
    return 0


def _display(path: Path) -> str:
    """Show paths inside the project relative to it, for shorter output."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)

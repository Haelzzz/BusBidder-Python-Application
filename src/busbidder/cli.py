"""Command-line interface.

For now it loads and validates the data and prints the load summary. The
interactive part (choose profile, view ranking, book) is built in a later task.
"""

import sys
from pathlib import Path

from busbidder.data_io.loader import load_marketplace
from busbidder.exceptions import BusBidderError, ConfigError
from busbidder.logging_setup import setup_logging
from busbidder.paths import PROJECT_ROOT
from busbidder.settings import load_settings


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
    print(f"\n{len(repository.offers)} offers available. Filtering, ranking and booking are not implemented yet.")
    return 0


def _display(path: Path) -> str:
    """Show paths inside the project relative to it, for shorter output."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)

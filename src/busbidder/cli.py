"""Command-line interface (stub).

The interactive CLI (choose profile, view ranking, book) is built in a later task.
"""

from busbidder.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    """Run the application and return a process exit code."""
    logger = setup_logging()
    logger.info("BusBidder started")
    print("BusBidder Spain - CLI not implemented yet.")
    return 0

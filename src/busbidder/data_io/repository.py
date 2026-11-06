"""In-memory store of the validated marketplace data.

Filtering, ranking and booking ask the repository for data and never deal
with files. The repository also enforces unique identifiers, like a primary
key in a database: adding a second record with a used ID is rejected.
"""

from collections.abc import Mapping
from types import MappingProxyType

from busbidder.exceptions import ErrorCategory, RecordValidationError
from busbidder.models import Company, Destination, Offer


class MarketplaceRepository:
    """Companies, destinations and offers, each indexed by ID."""

    def __init__(self) -> None:
        self._companies: dict[str, Company] = {}
        self._destinations: dict[str, Destination] = {}
        self._offers: dict[str, Offer] = {}

    def add_company(self, company: Company) -> None:
        _add_unique(self._companies, company.company_id, company, "company_id")

    def add_destination(self, destination: Destination) -> None:
        _add_unique(self._destinations, destination.destination_id, destination, "destination_id")

    def add_offer(self, offer: Offer) -> None:
        _add_unique(self._offers, offer.offer_id, offer, "offer_id")

    @property
    def companies(self) -> Mapping[str, Company]:
        """Read-only view of the companies by ID."""
        return MappingProxyType(self._companies)

    @property
    def destinations(self) -> Mapping[str, Destination]:
        """Read-only view of the destinations by ID."""
        return MappingProxyType(self._destinations)

    @property
    def offers(self) -> list[Offer]:
        """All offers, in the order they were loaded."""
        return list(self._offers.values())

    def find_offer(self, offer_id: str) -> Offer | None:
        return self._offers.get(offer_id)

    def offers_to(self, destination_id: str) -> list[Offer]:
        return [offer for offer in self._offers.values() if offer.destination.destination_id == destination_id]


def _add_unique(store: dict, key: str, item: object, field: str) -> None:
    if key in store:
        raise RecordValidationError(ErrorCategory.DUPLICATE_ID, field, f"{field} {key!r} is already used")
    store[key] = item

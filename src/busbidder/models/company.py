"""Bus companies (operators) in the marketplace."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Company:
    """A fictional bus operator.

    Immutable reference data: many offers share the same ``Company`` object.
    """

    company_id: str  # three-letter code, e.g. "SOL"
    name: str  # display name, e.g. "SolRuta"
    profile: str  # short description of the operator's strategy

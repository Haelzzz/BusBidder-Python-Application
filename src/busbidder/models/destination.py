"""Destinations served from the Madrid hub."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Destination:
    """A city reachable by bus from Madrid.

    Immutable reference data: many offers share the same ``Destination`` object.
    """

    destination_id: str  # three-letter code, e.g. "MAL"
    name: str  # display name, e.g. "Malaga"
    region: str  # autonomous community, e.g. "Andalusia"
    coastal: bool  # used by CostaLink's profile and possibly by later filters
    distance_km: int  # approximate road distance from Madrid
    base_duration_min: int  # typical direct bus journey time from Madrid

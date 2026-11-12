"""Custom exception hierarchy.

Every exception raised deliberately by the application derives from
``BusBidderError``, so the CLI can catch "our" errors in one place and let
genuine programming bugs surface with a traceback.
"""

from enum import StrEnum
from pathlib import Path


class BusBidderError(Exception):
    """Base class for all application-specific errors."""


class RegistryError(BusBidderError):
    """A plug-in could not be registered or looked up (duplicate/unknown name, wrong type)."""


class InvalidRequestError(BusBidderError):
    """A traveller request is internally inconsistent (e.g. end date before start date)."""


class BookingError(BusBidderError):
    """A booking cannot be made (unknown offer, not enough seats, invalid details)."""


class InvalidWeightsError(BusBidderError):
    """Criterion weights are unknown, negative, or do not total 1.0."""


class ConfigError(BusBidderError):
    """The settings file is missing, unreadable or contains invalid values."""


class DataFileError(BusBidderError):
    """A whole data file is unusable (missing, unreadable, wrong structure). Loading stops."""

    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path


class ErrorCategory(StrEnum):
    """Why a single record was rejected. Used for the load summary and the review file."""

    MISSING_FIELD = "missing_field"  
    MALFORMED_ID = "malformed_id"  
    INVALID_VALUE = "invalid_value"  
    INVALID_DATETIME = "invalid_datetime"  
    UNKNOWN_REFERENCE = "unknown_reference"  
    OUT_OF_RANGE = "out_of_range"  
    INCONSISTENT = "inconsistent"  
    NO_AVAILABILITY = "no_availability"  
    DUPLICATE_ID = "duplicate_id"  


class RecordValidationError(BusBidderError):
    """One record is invalid. The record is rejected; loading continues."""

    def __init__(self, category: ErrorCategory, field: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.field = field

"""Custom exception hierarchy.

Every exception raised deliberately by the application derives from
``BusBidderError``, so the CLI can catch "our" errors in one place and let
genuine programming bugs surface with a traceback.
"""


class BusBidderError(Exception):
    """Base class for all application-specific errors."""


class RegistryError(BusBidderError):
    """A plug-in could not be registered or looked up (duplicate/unknown name, wrong type)."""


class InvalidRequestError(BusBidderError):
    """A traveller request is internally inconsistent (e.g. end date before start date)."""

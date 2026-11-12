"""Regular expressions for the fixed-format text fields in the data files.

All patterns are used with ``fullmatch``, so they must match the whole value.

Regex is used only where a value is a fixed pattern of characters. Dates are
deliberately *not* checked with a regex: a pattern such as ``\\d{4}-\\d{2}-\\d{2}``
accepts 2026-06-31, so dates are parsed with ``datetime`` instead, which knows
the calendar.
"""

import re

CODE_RE = re.compile(r"[A-Z]{3}")

OFFER_ID_RE = re.compile(r"OF-(?P<company>[A-Z]{3})-(?P<destination>[A-Z]{3})-(?P<seq>\d{4})")

BOOKING_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
BOOKING_REF_RE = re.compile(rf"BB-[{BOOKING_REF_ALPHABET}]{{6}}")

# 24-hour clock time with leading zeros, 00:00 to 23:59.
TIME_RE = re.compile(r"(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)")

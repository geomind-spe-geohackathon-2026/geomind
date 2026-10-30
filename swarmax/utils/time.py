"""UTC timestamps and durations."""

import re
from datetime import datetime, timezone

_DURATION = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|min|h)$")
_SECONDS = {"ms": 0.001, "s": 1.0, "min": 60.0, "h": 3600.0}


def utc_now():
    """Return the current time as ISO 8601 text with a UTC offset."""
    return datetime.now(timezone.utc).isoformat()


def parse_duration(value):
    """Return seconds from a positive number or text such as ``"10min"``."""
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    match = _DURATION.match(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"duration = {value!r}; expected a positive number or text like '10min'")
    return float(match[1]) * _SECONDS[match[2]]

"""UTC timestamps and durations."""

import re
from datetime import datetime, timezone

_DURATION = re.compile(r"^(\d+(?:\.\d+)?)([a-z]+)$")
DURATION_UNITS = ("s", "min", "h", "d")
"""The units a duration may have; gemini converts each to seconds."""


def utc_now():
    """Return the current time as ISO 8601 text with a UTC offset."""
    return datetime.now(timezone.utc).isoformat()


def parse_duration(value):
    """Return seconds from a positive number or text such as ``"10min"``.

    NOTE: gemini converts (``gm.units.Quantity``), and a duration has one of ``DURATION_UNITS``;
    geomind holds no conversion factor.
    """
    import gemini as gm

    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    match = _DURATION.match(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"duration = {value!r}; expected a positive number or text like '10min'")
    if match[2] not in DURATION_UNITS:
        raise ValueError(f"duration = {value!r}; expected a unit of {', '.join(DURATION_UNITS)}")
    return float(gm.units.Quantity(float(match[1]), match[2]).to("s").value)

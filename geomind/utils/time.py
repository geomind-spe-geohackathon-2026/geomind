"""UTC timestamps and durations."""

import re
from datetime import datetime, timezone

_DURATION = re.compile(r"^(\d+(?:\.\d+)?)([a-z]+)$")


def utc_now():
    """Return the current time as ISO 8601 text with a UTC offset."""
    return datetime.now(timezone.utc).isoformat()


def parse_duration(value):
    """Return seconds from a positive number or text such as ``"10min"``.

    NOTE: gemini converts (``gm.units.Quantity``), so a duration takes any time unit gemini knows,
    such as ``ms``, ``s``, ``min``, ``h`` or ``d``; geomind holds no conversion factor.
    """
    import gemini as gm

    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    match = _DURATION.match(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"duration = {value!r}; expected a positive number or text like '10min'")
    try:
        return float(gm.units.Quantity(float(match[1]), match[2]).to("s").value)
    except gm.errors.ValidationError as error:
        raise ValueError(
            f"duration = {value!r}; expected a time unit gemini converts: {error}"
        ) from error

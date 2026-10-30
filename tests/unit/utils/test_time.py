"""Timestamps and durations."""

from datetime import datetime

import pytest

from swarmax.utils.time import parse_duration, utc_now


def test_utc_now_is_aware():
    """Times carry a zero offset."""
    assert datetime.fromisoformat(utc_now()).utcoffset().total_seconds() == 0


@pytest.mark.parametrize(
    ("value", "seconds"), [(5, 5.0), ("10min", 600.0), ("500ms", 0.5), ("1h", 3600.0)]
)
def test_parse_duration(value, seconds):
    """Numbers are seconds and text has a unit."""
    assert parse_duration(value) == seconds


@pytest.mark.parametrize("value", [0, -1, "soon", None])
def test_parse_duration_rejects_the_rest(value):
    """Only positive durations pass."""
    with pytest.raises(ValueError, match="expected a positive"):
        parse_duration(value)

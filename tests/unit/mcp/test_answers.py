"""The plain functions over a server's listing and answers: outline, check, tables, UTC."""

from datetime import timedelta

import pytest

from geomind.errors import ToolError
from geomind.mcp.answers import (
    argument_problem,
    arguments_of,
    is_future,
    rows_of,
    safe_file_name,
    summary_of,
    table_csv,
    tables_of,
    tzinfo_of,
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["latitude"],
    "properties": {
        "latitude": {"type": "number"},
        "start_date": {"type": "string", "format": "date"},
        "hourly_variables": {"type": "array", "items": {"type": "string"}},
        "temperature_unit": {"enum": ["celsius", "fahrenheit"]},
    },
}


def test_the_outline_of_arguments_names_type_and_required():
    """Each argument is one short text: its type, an enum's values, ``required``."""
    assert arguments_of(SCHEMA) == {
        "latitude": "number, required",
        "start_date": "string (date)",
        "hourly_variables": "array of string",
        "temperature_unit": 'one of "celsius", "fahrenheit"',
    }


def test_the_summary_is_the_first_sentence_cut_when_long():
    """A description's first sentence, marked when cut."""
    assert summary_of("Historical weather (1940–present). Requires dates.") == (
        "Historical weather (1940–present)."
    )
    assert summary_of("x" * 300, 10) == "x" * 9 + "…"


def test_a_missing_required_argument_comes_before_an_unknown_one():
    """``{query}``: ``latitude`` is missing; ``{latitude, hourly}``: ``hourly`` is unknown."""
    assert argument_problem(SCHEMA, {"query": "x"})[0] == "arguments.latitude"
    path, _, suggestions = argument_problem(SCHEMA, {"latitude": 1, "hourly": []})
    assert path == "arguments.hourly" and suggestions[0] == "hourly_variables"
    assert argument_problem(SCHEMA, {"latitude": 1}) is None
    assert (
        argument_problem({**SCHEMA, "additionalProperties": True}, {"latitude": 1, "a": 2}) is None
    )


def test_a_table_is_rows_or_equal_columns():
    """A list of objects and an object of equal lists are tables; others are not."""
    assert rows_of({"time": ["2025-01-01", "2025-01-02"], "t": [1, 2]})[1] == {
        "time": "2025-01-02",
        "t": 2,
    }
    assert rows_of({"time": ["a"], "t": [1, 2]}) is None and rows_of([1, 2]) is None
    structured = {"utc_offset_seconds": 3600, "daily": {"time": ["2025-01-01"], "t": [1]}}
    [table] = tables_of(structured)
    assert table["path"] == "structured.daily" and table["time_zone"] == "UTC+3600s"
    assert table["units"] is None and table["first"] == "2025-01-01"


def test_dates_after_the_day_of_the_call_are_future():
    """A date after the call's day is a forecast or a projection; the same day is not."""
    time = "2026-11-04T13:00:00+00:00"
    assert is_future({"end_date": "2026-11-05"}, [], time) is True
    assert is_future({"end_date": "2026-11-04"}, [], time) is False
    assert is_future({}, [{"first": "2025-01-01", "last": "2027-01-01"}], time) is True


def test_a_file_name_is_made_safe():
    """Unsafe characters become ``_``, empty and dot parts go, ``.csv`` is added."""
    assert safe_file_name("data/open-meteo Trondheim 2027") == "data/open-meteo_Trondheim_2027.csv"
    assert safe_file_name("../a b.CSV") == "a_b.CSV"
    assert safe_file_name(" / ") is None


def test_a_table_as_csv_has_its_times_in_utc():
    """Local times move to UTC, a time with an offset keeps it, null is empty."""
    rows = [
        {"time": "2026-07-01T12:00", "t": 20.5, "rh": None},
        {"time": "2026-07-01T13:00+00:00", "t": 21, "rh": 50},
    ]
    content, columns = table_csv(rows, tzinfo_of("Europe/Oslo", "test"))
    assert columns == ["t", "rh"]
    assert content.decode().splitlines() == [
        "time,t,rh",
        "2026-07-01T10:00:00Z,20.5,",
        "2026-07-01T13:00:00Z,21,50",
    ]
    assert tzinfo_of("UTC-7200s", "test").utcoffset(None) == timedelta(seconds=-7200)


def test_an_unknown_zone_is_refused():
    """A zone that is no IANA name is ``invalid_input`` on ``time_zone``."""
    with pytest.raises(ToolError) as caught:
        tzinfo_of("Mars/Olympus", "save_mcp_table")
    assert caught.value.path == "time_zone"

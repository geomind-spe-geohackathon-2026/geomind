"""What the MCP tools make of a server's listing and answers: plain functions over JSON values.

The listing's outline (each tool's server, name and arguments, short enough to stay in the
history), the check of a call's arguments against the tool's ``input_schema``, the tables of an
answer's structured content, the dates that mark an answer ``future``, and a table as CSV with its
times in UTC.
"""

import csv
import difflib
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from geomind.errors import ToolError

SUMMARY_CHARACTERS = 200
"""How long the summary of a tool's description is in the listing's outline."""
ENUM_SHOWN = 8
"""How many values of an enum the outline of an argument names."""
TEXT_CHARACTERS = 600
"""How much of a long answer's text its short form keeps: the server's heading and labels."""
SMALL_CHARACTERS = 150
"""How long a value of the structured content may be to stay in a long answer's short form."""
TIME_COLUMN = "time"
"""The column gemini reads a series' times from, and the one a server's table names its times."""
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def summary_of(text, limit=SUMMARY_CHARACTERS):
    """Return the first sentence of a description, cut to ``limit`` and marked when cut."""
    first = re.split(r"(?<=[.!?])\s|\n", (text or "").strip(), maxsplit=1)[0]
    return first if len(first) <= limit else first[: limit - 1] + "…"


def type_of(schema):
    """Return the type of an argument as text: ``number``, ``array of string``, ``a or b``."""
    if "enum" in schema:
        values = [json.dumps(value) for value in schema["enum"]]
        shown = ", ".join(values[:ENUM_SHOWN]) + (", …" if len(values) > ENUM_SHOWN else "")
        return f"one of {shown}"
    options = schema.get("anyOf") or schema.get("oneOf")
    if options:
        return " or ".join(type_of(option) for option in options)
    kind = schema.get("type", "any")
    kind = " or ".join(kind) if isinstance(kind, list) else kind
    if kind == "array":
        return f"array of {type_of(schema.get('items') or {})}"
    if schema.get("format"):
        return f"{kind} ({schema['format']})"
    return kind


def arguments_of(schema):
    """Return ``{argument: its type, and ', required' when it is}`` of an ``input_schema``."""
    required = set(schema.get("required") or ())
    return {
        name: type_of(item if isinstance(item, dict) else {})
        + (", required" if name in required else "")
        for name, item in (schema.get("properties") or {}).items()
    }


def tool_outline(server, row):
    """Return one tool of the listing's outline: server, name, read_only, summary, arguments."""
    return {
        "server": server,
        "name": row["name"],
        "read_only": row["read_only"],
        "summary": summary_of(row["description"]),
        "arguments": arguments_of(row["input_schema"]),
    }


def close_names(name, names):
    """Return the names that contain ``name`` or are close to it, the closest first."""
    found = [item for item in names if name and (name in item or item in name)]
    found += difflib.get_close_matches(name, names, n=3, cutoff=0.5)
    return list(dict.fromkeys(found))


def argument_problem(schema, arguments):
    """Return ``(path, message, suggestions)`` of the first argument the schema refuses, or None.

    A required argument that is missing, or an argument the schema does not name when it allows
    no others (``additionalProperties: false``). The server checks the rest.
    """
    properties = schema.get("properties") or {}
    for name in schema.get("required") or ():
        if name not in arguments:
            return f"arguments.{name}", f"arguments.{name} is required and missing", [name]
    if schema.get("additionalProperties") is False:
        for name in arguments:
            if name not in properties:
                return (
                    f"arguments.{name}",
                    f"arguments.{name} is not an argument of the tool",
                    close_names(name, list(properties)),
                )
    return None


def rows_of(value):
    """Return a table as its rows, ``[{column: value}]``, or ``None`` for a value that is none.

    A table is a list of objects, or an object of equally long lists (one per column).
    """
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        return value
    if isinstance(value, dict) and value and all(isinstance(item, list) for item in value.values()):
        lengths = {len(item) for item in value.values()}
        if len(lengths) == 1 and lengths != {0}:
            [length] = lengths
            return [{key: column[n] for key, column in value.items()} for n in range(length)]
    return None


def zone_of(structured):
    """Return the time zone the structured content names its times in, or ``None``.

    The IANA name of ``timezone``, else ``utc_offset_seconds`` as ``UTC+<seconds>s``.
    """
    if not isinstance(structured, dict):
        return None
    if isinstance(structured.get("timezone"), str) and structured["timezone"]:
        return structured["timezone"]
    offset = structured.get("utc_offset_seconds")
    if isinstance(offset, int) and not isinstance(offset, bool):
        return f"UTC{offset:+d}s"
    return None


def tables_of(structured):
    """Return ``[{path, rows, columns, units, time_zone, first, last}]`` of an answer's tables.

    ``path`` is the table's path in the answer (``structured.daily``), ``units`` the server's
    ``<name>_units`` beside it, and ``first`` and ``last`` its first and last time.
    """
    if not isinstance(structured, dict):
        return []
    found = []
    for key, value in structured.items():
        rows = rows_of(value)
        if rows is None:
            continue
        columns = list(dict.fromkeys(name for row in rows for name in row))
        units = structured.get(f"{key}_units")
        found.append(
            {
                "path": f"structured.{key}",
                "rows": len(rows),
                "columns": columns,
                "units": units if isinstance(units, dict) else None,
                "time_zone": zone_of(structured),
                "first": rows[0].get(TIME_COLUMN),
                "last": rows[-1].get(TIME_COLUMN),
            }
        )
    return found


def short_structured(structured):
    """Return the structured content without its long values: the tables are in ``tables``."""
    if not isinstance(structured, dict):
        return structured
    return {
        key: value
        for key, value in structured.items()
        if len(json.dumps(value, ensure_ascii=False)) <= SMALL_CHARACTERS
    }


def dates_in(value):
    """Return the dates of the ISO date and time texts in a JSON value."""
    if isinstance(value, str):
        return [date.fromisoformat(value[:10])] if DATE.match(value) else []
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return [found for item in items for found in dates_in(item)]


def is_future(arguments, tables, time):
    """Tell whether a date of the arguments or of a table lies after the day of the call.

    Such an answer cannot be measured: it is a forecast or a projection.
    """
    called = datetime.fromisoformat(time).date()
    bounds = [table[key] for table in tables for key in ("first", "last")]
    try:
        found = dates_in(arguments) + dates_in(bounds)
    except ValueError:
        found = []
    return any(day > called for day in found)


def safe_file_name(name):
    """Return ``name`` as a case file name: each part safe, empty parts left out, ``.csv``."""
    parts = [UNSAFE.sub("_", part).strip("_") for part in str(name).split("/")]
    parts = [part for part in parts if part and set(part) != {"."}]
    if not parts:
        return None
    if not parts[-1].lower().endswith(".csv"):
        parts[-1] += ".csv"
    return "/".join(parts)


def tzinfo_of(zone, tool_name):
    """Return the ``tzinfo`` of an IANA name or a ``UTC+<seconds>s``, or refuse the zone."""
    offset = re.fullmatch(r"UTC([+-]\d+)s", zone)
    if offset:
        return timezone(timedelta(seconds=int(offset.group(1))))
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolError(
            f"{tool_name}: time_zone = {zone!r}; expected an IANA zone such as 'Europe/Oslo'",
            path="time_zone",
        ) from None


def utc_text(value, zone):
    """Return a time of a table in UTC, ``YYYY-MM-DDTHH:MM:SSZ``; a date is its day's start.

    A time with its own offset keeps it; one without is a local time of ``zone``.
    """
    moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone)
    return moment.astimezone(timezone.utc).strftime(UTC_FORMAT)


def cell(value):
    """Return a value of a table as CSV text: a number as JSON writes it, null as empty."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return json.dumps(value)
    return str(value)


def table_csv(rows, zone):
    """Return ``(CSV bytes, value columns)`` of a table: ``time`` first, in UTC, then the rest."""
    columns = [name for name in dict.fromkeys(key for row in rows for key in row)]
    values = [name for name in columns if name != TIME_COLUMN]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([TIME_COLUMN, *values])
    for row in rows:
        writer.writerow([utc_text(row[TIME_COLUMN], zone), *(cell(row.get(n)) for n in values)])
    return out.getvalue().encode(), values

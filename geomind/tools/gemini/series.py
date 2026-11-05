"""Change a few rows of a series file, never the whole series typed again (QA-318).

A case lead repairing two bad days of a 365-day demand file retyped the series in ``save_profile``
and hit the output limit of one call five times. ``repair_series`` takes only the rows to change.
"""

import io
from typing import Any

from geomind.errors import ToolError
from geomind.stores.casefiles import case_files
from geomind.tools.base import tool
from geomind.tools.files import project_file
from geomind.tools.gemini.case import CASE_FILE, checked_name, state_case, store_case
from geomind.utils.strings import join_names

MOST_ROWS = 50
"""The most rows one repair changes: more is a new file, which the user gives."""
TIME_COLUMN = "time"
"""The name of the time column a repaired file is written with: the one ``set_case`` reads."""
TIME_NAMES = ("time", "date", "datetime", "timestamp")
"""The names a time column of a series file goes by, in any case."""


def file_bytes(context, file):
    """Return the bytes of ``file``: the run's case copy (a repaired file too), else the project's.

    QA-318: a file ``repair_series`` wrote could not be repaired again; it is a case file.
    """
    found = context.session.load_artifact(f"{CASE_FILE}{file}")
    if found is not None:
        return found
    return project_file(context, "repair_series", file)


def time_column(table):
    """Return the name of the time column of a table: by name, else its first column."""
    named = [name for name in table.columns if str(name).strip().lower() in TIME_NAMES]
    return named[0] if named else table.columns[0]


def value_column(table, time, column):
    """Return the column to change: ``column``, or the one value column; else raise."""
    values = [name for name in table.columns if name != time]
    if column is not None and column in values:
        return column
    if column is None and len(values) == 1:
        return values[0]
    raise ToolError(
        f"repair_series: column = {column!r}; expected one of {join_names(values)}",
        code="unknown_name",
        path="column",
        suggestions=[str(name) for name in values],
    )


def row_of(table, time, key):
    """Return the position of the row ``key`` names (a 0-based index, a time or a date), or None.

    ``None`` is a time the file lacks, which ``repair_series`` inserts (QA-318: a gap).
    """
    text = str(key).strip()
    if text.isdigit() and int(text) < len(table):
        return int(text)
    times = [str(item) for item in table[time]]
    for position, item in enumerate(times):
        if item == text or item[:10] == text[:10] == text:
            return position
    if parsed(text) is None:
        near = [item for item in times if item[:7] == text[:7]][:5] or times[:3]
        raise ToolError(
            f"repair_series: row {text!r} is no time of the file's {time!r} column, no time at "
            f"all, and no row index below {len(table)}; times near it: {join_names(near)}",
            code="unknown_name",
            path=f"rows.{text}",
            suggestions=near,
        )
    return None


def parsed(text):
    """Return a time text as a timestamp, or ``None`` when it is none."""
    import pandas as pd

    try:
        return pd.Timestamp(text)
    except (ValueError, TypeError):
        return None


def neighbours(table, time, name, position):
    """Return the rows before and after ``position`` as ``{time, value}``: what a repair is like.

    QA-318: a negative day of about 5200 kW was proposed as 500 kW; the neighbours say what the
    day is like, so a repaired value comes from them or from the user.
    """
    rows = [index for index in (position - 1, position + 1) if 0 <= index < len(table)]
    return [
        {"time": str(table.at[index, time]), "value": float(table.at[index, name])}
        for index in rows
    ]


def new_value(context, key, value):
    """Return the number a row takes: a number, or ``{"calculation": id}`` of an earlier one."""
    if isinstance(value, dict) and set(value) == {"calculation"}:
        found = {item.id: item for item in context.problem.calculations}.get(value["calculation"])
        if found is not None:
            return float(found.value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise ToolError(
        f"repair_series: rows.{key} = {value!r}; expected a number or {{\"calculation\": <id>}} "
        "of a calculation in the state",
        path=f"rows.{key}",
    )


def by_column(table, time, column, key, value):
    """Return ``{column: value}`` of one row: a value for ``column``, or one per column named.

    A day added to a file of several series needs a value of each: ``{"heat": 20, "cold": 3}``.
    """
    names = [str(name) for name in table.columns if name != time]
    if isinstance(value, dict) and value and set(value) <= set(names):
        return dict(value)
    return {value_column(table, time, column): value}


def inserted(table, time, key):
    """Return ``(table, position)`` with an empty row at the time ``key``, in time order."""
    import pandas as pd

    times = [parsed(str(item)) for item in table[time]]
    moment = parsed(str(key))
    position = next(
        (index for index, item in enumerate(times) if item is not None and item > moment),
        len(table),
    )
    shown = str(key) if len(str(table.at[0, time])) != 10 else moment.strftime("%Y-%m-%d")
    row = pd.DataFrame({column: [shown if column == time else None] for column in table.columns})
    table = pd.concat([table.iloc[:position], row, table.iloc[position:]], ignore_index=True)
    return table, position


def repaired(context, content, rows, column):
    """Return ``(csv bytes, changed rows)`` of a series with ``rows`` set, the rest as it was.

    A time the file lacks is inserted in order. The time column is written as ``time``, the name
    ``set_case`` reads (QA-318: a repaired file keeping ``date`` was refused five times).
    """
    import pandas as pd

    table = pd.read_csv(io.BytesIO(content))
    time = time_column(table)
    changed = []
    for key, value in rows.items():
        position = row_of(table, time, key)
        added = position is None
        if added:
            table, position = inserted(table, time, key)
        for name, given in by_column(table, time, column, key, value).items():
            number = new_value(context, key, given)
            table[name] = table[name].astype(float)
            old = table.at[position, name]
            table.at[position, name] = number
            changed.append(
                {
                    "row": position,
                    "time": str(table.at[position, time]),
                    "column": name,
                    "old": None if added or pd.isna(old) else float(old),
                    "new": number,
                    "added": added,
                    "neighbours": neighbours(table, time, name, position),
                }
            )
    buffer = io.StringIO()
    table.rename(columns={time: TIME_COLUMN}).to_csv(buffer, index=False)
    return buffer.getvalue().encode(), changed


def moved(node, old, new):
    """Return ``node`` with every reference to the file ``old`` made one to ``new``."""
    if isinstance(node, dict):
        return {key: moved(value, old, new) for key, value in node.items()}
    if isinstance(node, list):
        return [moved(value, old, new) for value in node]
    return new if node == old else node


@tool(effect="write", idempotent=False, reruns_in_replay=True)
async def repair_series(
    context,
    file: str,
    rows: dict[str, Any],
    name: str,
    column: str | None = None,
):
    """Change a few rows of a series file (a bad day, a gap) and keep it as data/<name>.csv.

    ``rows`` maps a time (or a 0-based row index) to a number or {"calculation": id}; a time the
    file lacks is added. Every other row stays as it is. Skill `setting-the-case`.
    """
    if not rows:
        raise ToolError("repair_series: rows = {}; expected the rows to change", path="rows")
    if len(rows) > MOST_ROWS:
        raise ToolError(
            f"repair_series: {len(rows)} rows; expected at most {MOST_ROWS}: ask the user for a "
            "corrected file instead",
            path="rows",
        )
    target = checked_name(f"data/{name}.csv")
    data = state_case(context) if context.problem.case is not None else None
    original = file_bytes(context, checked_name(file))
    content, changed = repaired(context, original, rows, column)
    shown = {"file": target, "changed": changed}
    if data is None or file not in case_files(data):
        await context.session.save_artifact(f"{CASE_FILE}{target}", content)
        return {
            **shown,
            "next": (
                f"name {target} in set_case (the demand's file) instead of {file}; its time "
                "column is `time`, so it needs no columns mapping"
            ),
        }
    version = await store_case(context, moved(data, file, target), {target: content})
    return {**shown, "version": version}

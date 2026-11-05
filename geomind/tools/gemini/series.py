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
TIME_NAMES = ("time", "date", "datetime", "timestamp")
"""The names a time column of a series file goes by, in any case."""


def file_bytes(context, data, file):
    """Return the bytes of ``file``: the case's copy when the case names it, else the project's."""
    if data is not None and file in case_files(data):
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
    """Return the position of the row ``key`` names: a 0-based index, or a time or date of it."""
    text = str(key).strip()
    if text.isdigit() and int(text) < len(table):
        return int(text)
    times = [str(item) for item in table[time]]
    for position, item in enumerate(times):
        if item == text or item[:10] == text[:10] == text:
            return position
    near = [item for item in times if item[:7] == text[:7]][:5] or times[:3]
    raise ToolError(
        f"repair_series: row {text!r} is no time of the file's {time!r} column nor a row index "
        f"below {len(table)}; times near it: {join_names(near)}",
        code="unknown_name",
        path=f"rows.{text}",
        suggestions=near,
    )


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


def repaired(context, content, rows, column):
    """Return ``(csv bytes, changed rows)`` of a series with ``rows`` set, the rest as it was."""
    import pandas as pd

    table = pd.read_csv(io.BytesIO(content))
    time = time_column(table)
    name = value_column(table, time, column)
    table[name] = table[name].astype(float)
    changed = []
    for key, value in rows.items():
        position = row_of(table, time, key)
        number = new_value(context, key, value)
        old = table.at[position, name]
        table.at[position, name] = number
        changed.append(
            {"row": position, "time": str(table.at[position, time]), "column": name,
             "old": None if pd.isna(old) else float(old), "new": number}
        )
    buffer = io.StringIO()
    table.to_csv(buffer, index=False)
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

    ``rows`` maps a time (or a 0-based row index) to a number or {"calculation": id}; every other
    row stays as it is. Skill `setting-the-case`.
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
    original = file_bytes(context, data, checked_name(file))
    content, changed = repaired(context, original, rows, column)
    shown = {"file": target, "changed": changed}
    if data is None or file not in case_files(data):
        await context.session.save_artifact(f"{CASE_FILE}{target}", content)
        return {
            **shown,
            "next": f"name {target} in set_case (the demand's file) instead of {file}",
        }
    version = await store_case(context, moved(data, file, target), {target: content})
    return {**shown, "version": version}

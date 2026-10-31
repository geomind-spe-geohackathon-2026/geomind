"""The tools over a project's results and documents."""

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.utils.strings import did_you_mean, join_names


def _part(mapping, name, what, reference):
    """Return one part of a stored result; a wrong name lists what exists."""
    if not isinstance(mapping, dict) or name not in mapping:
        names = mapping if isinstance(mapping, dict) else ()
        raise ToolError(
            f"read_result: {what} = {name!r}; expected one of {join_names(names)} in {reference}"
            f"{did_you_mean(name, names)}",
            code="unknown_name",
            path=what,
        )
    return mapping[name]


def _statistics(series):
    """Return ``{min, max, mean}`` of one series, each a Value."""
    unit = series.get("unit")
    numbers = [item for item in series["values"] if isinstance(item, (int, float))]
    if not numbers:
        empty = {"value": None, "unit": unit, "reason": "the series holds no numbers"}
        return {"min": empty, "max": empty, "mean": empty}
    mean = sum(numbers) / len(numbers)
    return {
        "min": {"value": min(numbers), "unit": unit},
        "max": {"value": max(numbers), "unit": unit},
        "mean": {"value": mean, "unit": unit},
    }


def _summary(stored):
    """Return ``{path: {field: {min, max, mean}}}`` of stored results."""
    return {
        path: {field: _statistics(series) for field, series in fields.items()}
        for path, fields in stored.items()
    }


def _series(series, start, end):
    """Return a slice of one series as a Value, with its times when they are stored."""
    value = {"value": series["values"][start:end], "unit": series.get("unit")}
    return {"time": series["time"][start:end], **value} if "time" in series else value


@tool(effect="read")
def read_result(
    context,
    reference: str,
    path: str | None = None,
    field: str | None = None,
    start: int | None = None,
    end: int | None = None,
):
    """Return one stored series as a value, or a summary of a result or of one module path.

    With ``path`` and ``field`` it returns the series, and ``start`` and ``end`` are sample
    positions, the first sample being 0. Without ``field`` it returns min, max and mean.
    """
    stored = context.session.load_artifact(reference)
    if stored is None:
        raise ToolError(
            f"read_result: reference = {reference!r}; expected a stored result",
            code="unknown_name",
            path="reference",
        )
    if path is None and field is not None:
        raise ToolError(f"read_result: field = {field!r}; expected a path too", path="path")
    if path is None:
        return _summary(stored)
    fields = _part(stored, path, "path", reference)
    if field is None:
        return _summary({path: fields})
    return _series(_part(fields, field, "field", reference), start, end)


@tool(effect="read")
def search_documents(context, query: str):
    """Search the documents of the project; return the best matches with id, title and text."""
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        raise ToolError(
            "search_documents: this run has no project; expected a workspace and one",
            code="not_allowed",
        )
    return workspace.documents(context.project, query)

"""The tools over a project's results and documents."""

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.runs import parse_time
from geomind.tools.gemini.stored import load_run

READ_UNITS = {
    "power": "MW",
    "temperature": "degC",
    "pressure": "bar",
    "volume_flow": "m3/h",
    "mass_flow": "kg/s",
}
"""The units in which the model reads a stored result: gemini's family keys for ``units=``."""


@tool(effect="read")
def read_result(
    context,
    reference: str,
    path: str | None = None,
    field: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Return one series of a stored run, or a summary of the run or of one module path.

    ``reference`` is what simulate returned. With ``path`` and ``field`` it returns the series
    ``{time, value, unit}``; ``start`` and ``end`` are ISO 8601 times, both inclusive. With only
    ``path`` it returns min, max and mean of each field of that module, and with neither of the
    whole run. Power is in MW, temperature in degC, pressure in bar, flows in m3/h or kg/s.
    """
    if path is None and field is not None:
        raise ToolError(f"read_result: field = {field!r}; expected a path too", path="path")
    _, _, results = load_run(context, reference, "read_result")
    if field is None:
        return results.summary(path=path, units=READ_UNITS)
    first, last = parse_time(start, "start", "read_result"), parse_time(end, "end", "read_result")
    return results.get(path, field, start=first, end=last, units=READ_UNITS)


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

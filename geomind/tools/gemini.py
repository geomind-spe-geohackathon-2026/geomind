"""The tools over a project's results and documents.

NOTE: this file has no ``import gemini`` yet. ``list_modules``, ``describe_module``,
``evaluate_module``, ``read_plant`` and ``simulate`` join it once gemini has its class registry,
``Module.describe()`` and a public plant loader, and they use only ``import gemini as gm``.
"""

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.utils.strings import did_you_mean, join_names


def _part(mapping, name, what, reference):
    """Return one part of a stored result; a wrong name lists what exists."""
    if not isinstance(mapping, dict) or name not in mapping:
        names = mapping if isinstance(mapping, dict) else ()
        raise ToolError(
            f"read_result: {what} = {name!r}; expected one of {join_names(names)} in {reference}"
            f"{did_you_mean(name, names)}"
        )
    return mapping[name]


@tool(effect="read")
def read_result(
    context, reference: str, path: str, field: str, start: int | None = None, end: int | None = None
):
    """Return a slice of a stored result: the values of one field of one module path.

    ``start`` and ``end`` are sample positions, the first sample being 0; leave them out for the
    whole series.
    """
    stored = context.session.load_artifact(reference)
    if stored is None:
        raise ToolError(f"read_result: reference = {reference!r}; expected a stored result")
    series = _part(_part(stored, path, "path", reference), field, "field", reference)
    return {
        "reference": reference,
        "path": path,
        "field": field,
        "unit": series.get("unit"),
        "start": start or 0,
        "values": series["values"][start:end],
    }


@tool(effect="read")
def search_documents(context, query: str):
    """Search the documents of the project; return the best matches with id, title and text."""
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        raise ToolError("search_documents: this run has no project; expected a workspace and one")
    return workspace.documents(context.project, query)

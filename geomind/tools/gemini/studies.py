"""The tools that list the studies of a chat and read one back."""

from geomind.tools.base import tool
from geomind.tools.gemini.references import reference_schema
from geomind.tools.gemini.stored import case_id, load_study, ran_case, study_index


@tool(effect="read")
def list_studies(context):
    """List this chat's studies (what ran, over which designs, whether current) and the project's.

    Skill `comparing-designs`.
    """
    from geomind.tools.gemini.plants import project_designs

    now = case_id(ran_case(context)) if context.problem.case is not None else None
    project = [{"project_study": item} for item in project_designs(context)["studies"]]
    return project + [
        {
            "study": entry["study"],
            "tool": entry["tool"],
            "method": entry["method"],
            "designs": entry["designs"],
            "best": entry["best"],
            "current": entry["case"] == now,
        }
        for entry in study_index(context)
    ]


@tool(effect="read", late_schemas={"study": reference_schema("study")})
def read_study(context, study: str):
    """Read a stored study: what ran, what came back, the designs it read and wrote, and its case.

    Skill `comparing-designs`.
    """
    record = load_study(context, study, "read_study")
    history = (record.get("result") or {}).get("history") if isinstance(record, dict) else None
    if not isinstance(history, list):
        return record
    return {"trials": trials_of(history), **record}


def _number(entry):
    """Return the number of a ``{value, unit}`` entry of gemini's history, or ``None``."""
    value = entry.get("value") if isinstance(entry, dict) else None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _span(entries):
    """Return ``{min, max, unit}`` of gemini's entries of one quantity, or ``None`` with none."""
    found = [
        (number, entry.get("unit")) for entry in entries if (number := _number(entry)) is not None
    ]
    if not found:
        return None
    numbers = [number for number, _ in found]
    return {"min": min(numbers), "max": max(numbers), "unit": found[0][1]}


def _options(entries):
    """Return the options (text values) a parameter took, each once, in order."""
    return list(dict.fromkeys(entry for entry in entries if isinstance(entry, str)))


def trials_of(history):
    """Return what every trial of an optimisation shows, from gemini's own history (QA-205).

    An answer rested on 27 of 240 trials read one by one: this gives the count, the feasible
    count (``violation`` 0 and a value) and, over the feasible trials, the least and greatest
    objective and value of each parameter, each as gemini gave it (no number of geomind's). The
    whole table is ``result.history``: ``read_stored`` it in pages (``start``) to the end.
    """
    feasible = [
        item
        for item in history
        if isinstance(item, dict) and item.get("violation") == 0 and _number(item) is not None
    ]
    names = list(
        dict.fromkeys(name for item in feasible for name in (item.get("parameters") or {}))
    )
    parameters = {}
    for name in names:
        entries = [(item.get("parameters") or {}).get(name) for item in feasible]
        span = _span(entries)
        parameters[name] = span if span is not None else {"options": _options(entries)}
    return {
        "count": len(history),
        "feasible": len(feasible),
        "objective": _span(feasible),
        "parameters": parameters,
        "note": (
            "over every trial of result.history; to read the table itself, read_stored it in "
            "pages (start, then each next) to the end, never a sample of it"
        ),
    }

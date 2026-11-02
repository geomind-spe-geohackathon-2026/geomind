"""The tools that list the studies of a chat and read one back."""

from geomind.tools.base import tool
from geomind.tools.gemini.references import reference_schema
from geomind.tools.gemini.stored import case_id, load_study, ran_case, study_index


@tool(effect="read")
def list_studies(context):
    """List the studies stored in this chat: what ran, over which designs, and whether current.

    Each item is ``{study, tool, method, designs, best, current}``: the ``study/<name>`` key, the
    study tool and the gemini method it ran, the names of the plants it ran over, the reference of
    the design it recommends (``null`` when it has none) and ``current``, whether the state's case
    is still the case it ran on. A study that is not current ran on an older case: run it again
    under a new name before relying on it.
    """
    now = case_id(ran_case(context)) if context.problem.case is not None else None
    return [
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

    ``study`` is a key such as ``study/<name>`` that a study tool returned or ``list_studies``
    listed. Returns ``study`` (gemini's study file as it ran), ``result`` (gemini's plain form of
    what came back), ``designs`` (``{read, wrote}`` references), ``case`` (the id of the case it
    ran on), ``tool`` and ``versions``.
    """
    return load_study(context, study, "read_study")

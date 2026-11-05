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
    return load_study(context, study, "read_study")

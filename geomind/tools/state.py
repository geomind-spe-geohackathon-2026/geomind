"""The tool that writes the problem state."""

from typing import Any

from geomind.errors import ToolError
from geomind.tools.base import tool

CASE_KEYS = ("case", "case_origin")


def check_no_case(changes):
    """Raise when a change reaches the case, which only set_case writes after gemini checks it."""
    for position, change in enumerate(changes):
        path = change.get("path") if isinstance(change, dict) else None
        key = path.split("/")[1] if isinstance(path, str) and path.count("/") >= 1 else None
        if key in CASE_KEYS:
            raise ToolError(
                f"update_state: changes[{position}].path = {path!r}; the case is written only by "
                "set_case, which gemini validates",
                code="not_allowed",
                path=f"changes[{position}].path",
            )


@tool(effect="write", idempotent=False, reruns_in_replay=True)
async def update_state(context, changes: list[dict[str, Any]]):
    """Change the problem state with JSON Patch operations (add, replace, remove).

    Paths are JSON Pointers under goal, requirements, assumptions, design, results, verification
    or questions; the case is set only with set_case. Items of requirements, assumptions, results
    and questions are addressed by id, as in /assumptions/A1/confirmed; add to /requirements/-
    appends an item that has an id. A requirement has id, text, status and, when a requirement
    of the case judges it, case_requirement: that requirement's name. An assumption
    has id, text, value, source (user, agent or default) and confirmed; a result id, summary,
    reference; a question id, text.
    """
    check_no_case(changes)
    return {"version": await context.session.change_state(changes)}

"""The tool that writes the problem state."""

from typing import Any

from geomind.tools.base import tool


@tool(effect="write", idempotent=False, reruns_in_replay=True)
async def update_state(context, changes: list[dict[str, Any]]):
    """Change the problem state with JSON Patch operations (add, replace, remove).

    Paths are JSON Pointers under goal, requirements, assumptions, design, results, verification,
    questions or case (set_case sets and checks a case). Items of requirements, assumptions, results
    and questions are addressed by id, as in /assumptions/A1/confirmed; add to /requirements/-
    appends an item that has an id. A requirement has id, text, metric, target, tolerance, status;
    an assumption id, text, value, source (user, agent or default), confirmed; a result id,
    summary, reference; a question id, text.
    """
    return {"version": await context.session.change_state(changes)}

"""How the state's case differs from the case the user or the project gave, and its approval.

A design is verified only on the case the user gave (``case_origin``). Every difference of the
current case from it, a constraint, a demand value, a file, the time or a price, is listed here, so
no agent passes verification by weakening the case. Only the user approves a difference, through
the design loop's question, and the driver then calls ``accept_case``.
"""

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.case import digests, file_contents, keep_files, state_case


def constraint_changes(given, now):
    """Return the constraints removed from and added to the given list."""
    removed = [
        {"path": "constraints", "change": "removed", "given": item}
        for item in given
        if item not in now
    ]
    added = [
        {"path": "constraints", "change": "added", "now": item} for item in now if item not in given
    ]
    return removed + added


def section_changes(name, given, now):
    """Return the changes of one section: by key for an object, else the section as a whole."""
    if given == now:
        return []
    if name == "constraints":
        return constraint_changes(given or [], now or [])
    if not (isinstance(given, dict) and isinstance(now, dict)):
        return [{"path": name, "change": "changed", "given": given, "now": now}]
    return [
        {"path": f"{name}.{key}", "change": "changed", "given": given.get(key), "now": now.get(key)}
        for key in sorted(set(given) | set(now))
        if given.get(key) != now.get(key)
    ]


def file_changes(given, now):
    """Return the files whose content differs from the given ones."""
    return [
        {"path": f"file {name}", "change": "changed"}
        for name in sorted(set(given) | set(now))
        if given.get(name) != now.get(name)
    ]


def changes_of(context):
    """Return every difference of the state's case from ``case_origin``; ``[]`` without both."""
    origin, case = context.problem.case_origin, context.problem.case
    if origin is None or case is None:
        return []
    given = origin["case"]
    found = [
        change
        for name in sorted(set(given) | set(case))
        for change in section_changes(name, given.get(name), case.get(name))
    ]
    now = digests(file_contents(context, case, {}))
    return found + file_changes(origin["files"], now)


@tool(effect="read")
def case_changes(context):
    """List how the state's case differs from the case the user or the project gave.

    Each item has ``path`` (a section, ``section.key``, ``constraints`` or ``file <name>``),
    ``change`` (``changed``, ``removed`` or ``added``) and the ``given`` and ``now`` values. An
    empty list means the case is the one the user gave. A design is verified only on that case:
    any difference waits for the user's approval.
    """
    return changes_of(context)


@tool(effect="write", idempotent=False, reruns_in_replay=True)
async def accept_case(context):
    """Make the state's case the one the user gave, after the user approved its changes.

    Only the design loop's driver holds this tool, after the user answered its question.
    """
    data = state_case(context)
    if context.problem.case_origin is None:
        raise ToolError("accept_case: the problem state has no case the user gave; expected one")
    files = file_contents(context, data, {})
    await keep_files(context, files)
    value = {"case": data, "files": digests(files)}
    version = await context.session.change_state(
        [{"op": "replace", "path": "/case_origin", "value": value}]
    )
    return {"version": version}

"""How the state's case differs from the case the user or the project gave, and its approval.

A design is verified only on the case the user gave (``case_origin``), the content of every file
it names included, the economics and the series. Every difference of the current case from it, a
requirement, a demand value, a file, the time or a price, is listed here, so
no agent passes verification by weakening the case. Only the user approves a difference, through
the design loop's question, and the driver then calls ``accept_case``.
"""

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.case import digests, file_contents, keep_files, state_case


def change_of(path, given, now):
    """Return one change: ``added`` if only ``now`` has a value, ``removed`` if only ``given``."""
    kind = "added" if given is None else "removed" if now is None else "changed"
    return {"path": path, "change": kind, "given": given, "now": now}


def keyed_changes(prefix, given, now):
    """Return the changes by key of two mappings, each key under ``prefix``."""
    return [
        change_of(f"{prefix}.{key}", given.get(key), now.get(key))
        for key in sorted(set(given) | set(now))
        if given.get(key) != now.get(key)
    ]


def by_name(requirements):
    """Return ``{name: requirement}`` of a list of case requirements."""
    return {item.get("name"): item for item in requirements or []}


def section_changes(name, given, now):
    """Return the changes of one section: by key for an object, by name for the requirements."""
    if given == now:
        return []
    if name == "requirements":
        return keyed_changes(name, by_name(given), by_name(now))
    if not (isinstance(given, dict) and isinstance(now, dict)):
        return [change_of(name, given, now)]
    return keyed_changes(name, given, now)


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

    Skill `setting-the-case`.
    """
    return changes_of(context)


@tool(effect="write", idempotent=False, reruns_in_replay=True)
async def accept_case(context):
    """Make the state's case the one the user gave, after the user approved its changes.

    Skill `setting-the-case`.
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

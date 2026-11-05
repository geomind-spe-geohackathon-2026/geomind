"""The one-line sentences of what a call does, for approval cards and the lead's notes.

They read only a call's tool name and input, so the engine (approval cards) and the agents (the
project lead's note of denied cards, QA-288; the case changes it reports) share them from here: an
agent may not import the engine.
"""

import json

DENIED_BY_USER = "denied by the user"
"""The reason of a card the user denied without words."""


def _leaves(node, prefix=""):
    """Return the dotted paths of the leaves of a nested change, a ``{value, unit}`` one leaf."""
    if not isinstance(node, dict) or not node or "value" in node:
        return [prefix] if prefix else []
    found = []
    for key, child in node.items():
        found += _leaves(child, f"{prefix}.{key}" if prefix else str(key))
    return found


def _bound(side):
    """Return one range bound as text: ``300 m3/h`` or a plain number."""
    if isinstance(side, dict):
        return f"{side.get('value')} {side.get('unit') or ''}".strip()
    return str(side)


def _listed(items, most=6):
    """Return up to ``most`` items joined, with how many more."""
    items = list(items)
    shown = ", ".join(items[:most])
    return f"{shown} and {len(items) - most} more" if len(items) > most else shown


def call_summary(tool, tool_input):
    """Return one plain sentence of what a call does, for its approval card, or ``None``.

    The plant tools sent hundreds of lines of JSON to approve with no word on what changes.
    """
    summary = SUMMARIES.get(tool)
    return None if summary is None else summary(tool_input or {})


def _build_summary(item):
    """Return the sentence of a ``build_plant`` call: its class or modules and connections."""
    plant = item.get("plant") or {}
    modules = plant.get("modules") or {}
    kind = plant.get("type") or item.get("from_class")
    what = f"of class {kind}" if kind else f"with {len(modules)} modules"
    links = len(plant.get("connections") or [])
    tail = f" and {links} connections" if links else ""
    return f"Build plant '{item.get('name')}' {what}{tail}."


def _patch_summary(item):
    """Return the sentence of a ``patch_plant`` call: how many values change, and which."""
    changes = item.get("changes") or {}
    if isinstance(changes, list):
        listed = [change for change in changes if isinstance(change, dict)]
        paths = [str(change.get("path")).removeprefix("plant.") for change in listed]
    else:
        paths = _leaves(changes)
    return (
        f"Change {len(paths)} value(s) of {item.get('design')} and save it as "
        f"'{item.get('name')}': {_listed(paths)}."
    )


def _ranges_summary(item):
    """Return the sentence of a ``set_ranges`` call: each range and the ranges removed."""
    parts = [
        f"{path} {_bound(bounds.get('min'))} to {_bound(bounds.get('max'))}"
        for path, bounds in (item.get("ranges") or {}).items()
        if isinstance(bounds, dict) and bounds
    ]
    dropped = [p for p, b in (item.get("ranges") or {}).items() if not b]
    text = f"Search ranges on {item.get('design')}, saved as '{item.get('name')}': "
    text += _listed(parts) or "none"
    return text + (f"; ranges removed: {_listed(dropped)}" if dropped else "") + "."


def _lesson_summary(item):
    """Return the sentence of a ``write_lesson`` call: every entry it keeps in the memory."""
    from geomind.tools.memory import lessons_of

    kept = [
        f"{entry.get('id')} ({entry.get('kind')} for {entry.get('role')}, from "
        f"{entry.get('source')}): {entry.get('text')}"
        for entry in lessons_of(item)
    ]
    return f"Keep {len(kept)} entries in the memory:\n" + "\n".join(f"- {k}" for k in kept)


def _value_text(node):
    """Return a leaf of a change as text: ``0.5 EUR/(W/K)``, a plain value, or ``removed``."""
    if isinstance(node, dict) and "value" in node:
        return f"{node.get('value')} {node.get('unit') or ''}".strip()
    return "removed" if node is None else json.dumps(node, ensure_ascii=False, default=str)


def _leaf_values(node, prefix=""):
    """Return ``(path, value text)`` of each leaf of a nested change, a ``{value, unit}`` one."""
    if not isinstance(node, dict) or not node or "value" in node:
        return [(prefix, _value_text(node))] if prefix else []
    found = []
    for key, child in node.items():
        found += _leaf_values(child, f"{prefix}.{key}" if prefix else str(key))
    return found


def _case_summary(item):
    """Return the sentence of a ``set_case`` call: where the case comes from and what changes.

    Every economics value is shown with its unit: the card listed only paths, so a user could not
    see the values differ from the ones just approved (QA-168).
    """
    changed = _leaves(item.get("changes") or {}) + [
        f"economics.{path}" for path in _leaves(item.get("economics") or {})
    ]
    files = item.get("files") or []
    if item.get("source") in SOURCE_WORDS:
        text = SOURCE_WORDS[item["source"]]
        text += f", then change {_listed(changed)}" if changed else ""
    else:
        text = f"Change the case: {_listed(changed)}" if changed else "Set the case"
    text += (f"; files {_listed(files)}" if files else "") + "."
    priced = _leaf_values(item.get("economics") or {})
    if priced:
        text += "\nEconomics values:\n" + "\n".join(f"- {p}: {v}" for p, v in priced)
    return text


SOURCE_WORDS = {
    "project": "Load the project's saved case",
    "origin": "Start again from the case the user or the project gave",
}


def _differing(old, new, prefix=""):
    """Return the dotted paths where two case dicts differ, a ``{value, unit}`` one leaf."""
    nested = isinstance(old, dict) and isinstance(new, dict)
    if nested and "value" not in old and "value" not in new:
        found = []
        for key in sorted(set(old) | set(new), key=str):
            path = f"{prefix}.{key}" if prefix else str(key)
            found += _differing(old.get(key), new.get(key), path)
        return found
    return [] if old == new else [prefix or "case"]


def _leaf(node, path):
    """Return the value at a dotted path of a case dict as short text, or ``none``."""
    for key in path.split("."):
        node = node.get(key) if isinstance(node, dict) else None
    if isinstance(node, dict) and "value" in node:
        return f"{node.get('value')} {node.get('unit') or ''}".strip()
    if node is None or isinstance(node, (dict, list)):
        return "none" if node is None else "..."
    return str(node)


SUMMARIES = {
    "build_plant": _build_summary,
    "patch_plant": _patch_summary,
    "set_ranges": _ranges_summary,
    "set_case": _case_summary,
    "write_lesson": _lesson_summary,
}
"""The sentence of each tool whose approval card says what the call does."""

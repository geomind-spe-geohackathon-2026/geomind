"""Starting plants: plant files of the Knowledge base a design starts from, never typed by hand.

The agents re-typed reference plants by hand and never reached a superstructure, which takes tens
of kilobytes of plant file: a scripted ``evolve`` on one found a far cheaper design in about a
minute. ``list_starts`` names the plant files (``.json``) the Knowledge base holds and
``start_plant`` stores one as a design, as ``build_plant`` would. The package itself holds no
plant: what a project starts from is data the Knowledge base gives.
"""

import json

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.stored import save_design
from geomind.tools.knowledge import PREFIX, has_knowledge
from geomind.utils.strings import did_you_mean

SUFFIX = ".json"


def start_documents(context):
    """Return the names of the Knowledge base's JSON documents, ``[]`` without one."""
    workspace = context.session.workspace
    if not has_knowledge(workspace):
        return []
    names = [item["name"] for item in workspace.knowledge_files()]
    return [name for name in names if name.lower().endswith(SUFFIX)]


def start_name(document):
    """Return the name a start goes by: its document's name without folders and ``.json``."""
    return document.rsplit("/", 1)[-1][: -len(SUFFIX)]


def read_start(context, document):
    """Return ``(plant file dict, gemini plant)`` of a document, or ``None`` when it is no plant.

    A JSON document gemini cannot read as a plant (prices, a table) is no start.
    """
    import gemini as gm

    content = context.session.workspace.knowledge_file(document)
    try:
        data = json.loads(content)
        return data, gm.Plant.from_dict(data)
    except Exception:  # noqa: BLE001
        return None


def starts(context):
    """Return ``{name: (document, data, plant)}`` of every plant file of the Knowledge base."""
    found = {}
    for document in start_documents(context):
        read = read_start(context, document)
        if read is not None:
            found[start_name(document)] = (document, *read)
    return found


def start_entry(name, document, data, plant):
    """Return one start as the model reads it: its document, class, structures and what it is."""
    count = len(plant.structures())
    entry = {
        "start": name,
        "document": f"{PREFIX}{document}",
        "type": data.get("type"),
        "structures": count,
        "about": data.get("about") or None,
    }
    if count > 1:
        entry["note"] = "a superstructure: size_plant, then one evolve_structure"
    return entry


def next_calls(reference, structures):
    """Return the calls that follow a start, in one line."""
    if structures > 1:
        return (
            f"size_plant(design={reference!r}, name=...), then ONE "
            "evolve_structure(design=<the sized design>, objectives=['lcts', 'co2'], name=...)"
        )
    return (
        f"work on {reference}: size_plant, or run_study(designs=[{reference!r}], prepare=['size'])"
    )


@tool(effect="read")
async def list_starts(context):
    """List the plant files of the Knowledge base a design starts from with start_plant.

    Skill `designing-a-plant`.
    """
    found = await runtime.in_gemini_thread(starts, context)
    return [start_entry(name, *item) for name, item in found.items()]


@tool(effect="write")
async def start_plant(context, start: str, name: str):
    """Store a starting plant file (list_starts) as design/<name>; return its issues and next calls.

    Skill `designing-a-plant`.
    """
    from geomind.tools.gemini.plants import free_name, plant_issues, stored_twins

    found = await runtime.in_gemini_thread(starts, context)
    if start not in found:
        names = list(found)
        listed = ", ".join(names) or "none: the Knowledge base holds no plant file"
        raise ToolError(
            f"start_plant: start = {start!r}; expected one of list_starts: {listed}"
            f"{did_you_mean(start, names)}",
            code="unknown_name",
            path="start",
            suggestions=names,
        )
    free_name(name, "start_plant")
    _, _, built = found[start]
    design = await save_design(context, name, built)
    issues = await runtime.in_gemini_thread(plant_issues, context, built)
    twins = await runtime.in_gemini_thread(stored_twins, context, built)
    structures = len(built.structures())
    return {
        "design": design,
        "start": start,
        "structures": structures,
        **issues,
        **twins,
        "next": next_calls(design, structures),
    }

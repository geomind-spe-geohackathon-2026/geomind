"""The memory tools: search, read and write the shared memory.

The case, design and analysis teams have all of them; the reviewer and the explainer read the
knowledge only, never experience (``search_knowledge``, ``read_knowledge``).
"""

from typing import Any, Literal

from geomind import runtime
from geomind.errors import ToolError
from geomind.stores.memory import (
    checked_knowledge,
    checked_section,
    search_experience,
)
from geomind.stores.memory import search_knowledge as search_knowledge_entries
from geomind.tools.base import tool

SHOWN_ENTRIES = 8
"""The most entries of each section ``search_memory`` returns, best first."""


def memory_of(context, tool_name):
    """Return the run's memory, or raise ``not_allowed`` when it is off."""
    memory = getattr(context.session, "memory", None)
    if memory is None:
        raise ToolError(
            f"{tool_name}: the memory is off for this run (GEOMIND_MEMORY); work from the case, "
            "the files and the user",
            code="not_allowed",
        )
    return memory


def case_features(case):
    """Return the general features of a ``gm.Case`` in SI units, ``None`` where it has none.

    They are the demand's peak and mean, the supply temperatures, the depth and the time step.
    """
    demand = case.demand

    def series(service, reduce):
        values = getattr(service, "power", None) if service is not None else None
        return float(reduce(values)) if values is not None and len(values) else None

    heating = getattr(demand, "heating", None)
    cooling = getattr(demand, "cooling", None)
    reservoir = getattr(case.site, "reservoir", None) if case.site is not None else None
    step = getattr(case.time, "step", None)
    return {
        "heating_peak": series(heating, max),
        "heating_mean": series(heating, lambda values: sum(values) / len(values)),
        "cooling_peak": series(cooling, max),
        "cooling_mean": series(cooling, lambda values: sum(values) / len(values)),
        "heating_supply": getattr(heating, "supply_temperature", None),
        "cooling_supply": getattr(cooling, "supply_temperature", None),
        "depth": getattr(reservoir, "reference_depth", None),
        "step": float(step) if isinstance(step, (int, float)) else None,
    }


def state_features(context):
    """Return the features of the state's case, or ``None`` when there is none."""
    from geomind.tools.gemini.case import case_of

    if context.problem.case is None:
        return None
    return case_features(case_of(context))


@tool(effect="read")
def search_memory(context, query: str, section: Literal["knowledge", "experience"] | None = None):
    """Search the shared memory: cited reference values, and designs that passed before.

    ``knowledge`` returns entries that hold a word of ``query``, each with its source (title,
    publisher, year, page or link, price year and currency for money) and ``status``
    (``verified``, ``secondary`` or ``placeholder``). ``experience`` returns past designs whose
    case is at least the ``memory_similarity`` setting alike to the state's case, each with its
    ``similarity``: a starting point only, never a result. Without ``section``, both.
    """
    memory = memory_of(context, "search_memory")
    found = {}
    if section in (None, "knowledge"):
        found["knowledge"] = search_knowledge_entries(memory, query)[:SHOWN_ENTRIES]
    if section in (None, "experience"):
        features = state_features(context)
        threshold = runtime.get("memory_similarity")
        if features is None or threshold is None:
            found["experience"] = []
            found["note"] = "experience needs the state's case and the memory_similarity setting"
        else:
            entries = search_experience(memory, features, threshold)
            found["experience"] = entries[:SHOWN_ENTRIES]
            found["threshold"] = threshold
    return found


@tool(effect="read")
def read_memory(context, section: Literal["knowledge", "experience"], id: str):
    """Return one entry of the memory by its section and id."""
    memory = memory_of(context, "read_memory")
    for entry in memory.entries(checked_section(section)):
        if entry.get("id") == id:
            return entry
    raise ToolError(
        f"read_memory: {section} has no entry {id!r}; expected an id that search_memory gave",
        code="unknown_name",
        path="id",
    )


@tool(effect="read")
def search_knowledge(context, query: str):
    """Search the shared memory's cited reference values only, never past designs.

    Returns the entries that hold a word of ``query``, each with its source (title, publisher,
    year, page or link, price year and currency for money) and ``status`` (``verified``,
    ``secondary`` or ``placeholder``).
    """
    memory = memory_of(context, "search_knowledge")
    return {"knowledge": search_knowledge_entries(memory, query)[:SHOWN_ENTRIES]}


@tool(effect="read")
def read_knowledge(context, id: str):
    """Return one cited reference value of the memory's knowledge by its id."""
    memory = memory_of(context, "read_knowledge")
    for entry in memory.entries("knowledge"):
        if entry.get("id") == id:
            return entry
    raise ToolError(
        f"read_knowledge: knowledge has no entry {id!r}; expected an id that search_knowledge "
        "gave",
        code="unknown_name",
        path="id",
    )


@tool(effect="write", idempotent=True)
def write_memory(context, entry: dict[str, Any]):
    """Add a cited reference value to the memory's knowledge, for later runs.

    ``entry`` is ``{id, item, value, unit, title, publisher, year, page or link, status, note}``,
    with ``price_year`` and ``currency`` for money; a value without its source is refused. Past
    designs are written by the design loop alone, after one passed verification.
    """
    memory = memory_of(context, "write_memory")
    entry = {**checked_knowledge(entry), "origin_run": context.session.state.run_id}
    memory.add("knowledge", entry)
    return {"written": entry["id"]}

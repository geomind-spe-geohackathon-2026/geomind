"""The memory tools: the team's experience, read by the case, design and analysis teams.

Experience is past designs (written by code after the reviewer passed them) and the curator's
lessons and the user's facts. The reviewer and the explainer never read it; cited values are the
knowledge base's (``geomind/tools/knowledge.py``).
"""

from typing import Literal

from geomind import runtime
from geomind.errors import ToolError
from geomind.stores.memory import checked_lesson, lessons_for, search_experience
from geomind.tools.base import tool

MEMORY_TOOLS = frozenset({"search_memory", "read_memory", "write_lesson"})
"""The tools that need the memory: a run with the memory off does not offer them."""
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
def search_memory(context):
    """Return what the team learned before: designs that passed on alike cases, and lessons.

    ``experience`` holds past designs whose case is at least the ``memory_similarity`` setting
    alike to the state's case, each with its ``similarity``: a starting point only, never a
    result. ``lessons`` holds the general lessons of your role and the facts the user gave.
    Cited values are not here: search the knowledge base (``search_knowledge``).
    """
    memory = memory_of(context, "search_memory")
    found = {"lessons": lessons_for(memory, role_of(context))[:SHOWN_ENTRIES]}
    features = state_features(context)
    threshold = runtime.get("memory_similarity")
    if features is None or threshold is None:
        note = "past designs need the state's case and the memory_similarity setting"
        return {"experience": [], "note": note, **found}
    entries = search_experience(memory, features, threshold)
    return {"experience": entries[:SHOWN_ENTRIES], "threshold": threshold, **found}


def role_of(context):
    """Return the snake name of the agent that makes the call, or ``None``."""
    agent = getattr(context.session, "agent", None)
    return getattr(agent, "name", None)


@tool(effect="read")
def read_memory(context, id: str):
    """Return one experience entry by the id ``search_memory`` gave."""
    memory = memory_of(context, "read_memory")
    for entry in memory.entries("experience"):
        if entry.get("id") == id:
            return entry
    raise ToolError(
        f"read_memory: experience has no entry {id!r}; expected an id that search_memory gave",
        code="unknown_name",
        path="id",
    )


@tool(effect="write", idempotent=True)
def write_lesson(
    context,
    id: str,
    kind: Literal["lesson", "user_fact"],
    role: str,
    text: str,
    source: str,
):
    """Keep a general lesson for one role, or a fact the user gave, in the memory's experience.

    A ``lesson`` is method for ``role`` (an agent's snake name such as ``design_lead``, or
    ``all``) in words, with no number: a project's values never become a rule. A ``user_fact``
    is what the user said (``source`` ``user``), such as the units they read. ``source`` says
    where it came from: ``user``, ``reviewer``, ``gemini`` or the agent that learned it. Past
    designs are written by code alone, after the reviewer passed them.
    """
    memory = memory_of(context, "write_lesson")
    origin = {"run": context.session.state.run_id, "source": source}
    entry = {"id": id, "kind": kind, "role": role, "text": text, "origin": origin}
    entry["project_id"] = context.project
    memory.add("experience", checked_lesson(entry))
    return {"written": id, "kind": kind}


def keep_design(context, found, rejected):
    """Keep a design that passed gemini's checks and the reviewer as experience, when on.

    The entry holds the case's general features, the design and its result, the KPIs, the
    verdict and the failures of the rejected rounds (``rejected``, lists of check names), never a
    rule made of the case's numbers. Code writes it, never a model; a replay keeps nothing, since
    its run was kept the first time.
    """
    from geomind.tools.gemini.case import case_of

    session = context.session
    memory = getattr(session, "memory", None)
    if memory is None or getattr(session.engine, "recorded", None):
        return
    problem = context.problem
    memory.add(
        "experience",
        {
            "id": session.state.run_id,
            "features": case_features(case_of(context)),
            "case": case_summary(problem.case),
            "design": problem.design_state.reference,
            "result": problem.verification.get("result"),
            "kpis": problem.verification.get("kpis"),
            "verdict": "passed",
            "families": problem.design.get("families") if problem.design else None,
            "lessons": [f"rejected before: {', '.join(names)}" for names in rejected],
            "origin": {"run": session.state.run_id, "source": "code"},
            "project_id": context.project,
        },
    )


def case_summary(case):
    """Return the sections a case sets and the name of each demand service, as general features."""
    demand = case.get("demand") or {}
    return {"sections": sorted(case), "services": sorted(demand)}

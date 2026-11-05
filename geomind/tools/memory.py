"""The memory tools: the team's experience, read by the case, design and analysis teams.

Experience is past designs (written by code after the reviewer passed them) and the curator's
lessons and the user's facts. The reviewer and the explainer never read it; cited values are the
knowledge base's (``geomind/tools/knowledge.py``).
"""

import difflib
from typing import Literal

from pydantic import BaseModel, ConfigDict

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
            f"{tool_name}: the memory is off for this run (GEOMIND_MEMORY, or the workspace for "
            "this project); work from the case, the files and the user",
            code="not_allowed",
        )
    return memory


def from_store(tool_name, action, *arguments):
    """Call the memory store, answering ``memory_unavailable`` with its error when it fails.

    A backend's store can fail (a database gone); the model reads why and goes on without the
    memory, never an ``internal`` error (B4).
    """
    try:
        return action(*arguments)
    except ToolError:
        raise
    except Exception as error:
        raise ToolError(
            f"{tool_name}: the memory store failed ({type(error).__name__}: {error}); go on "
            "without the memory",
            code="memory_unavailable",
        ) from error


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

    Skill `memory`.
    """
    memory = memory_of(context, "search_memory")
    role = role_of(context)
    if role == CURATOR:
        lessons = from_store("search_memory", memory_lessons, memory)
    else:
        lessons = from_store("search_memory", lessons_for, memory, role)
    found = {"lessons": lessons[:SHOWN_ENTRIES]}
    features = state_features(context)
    threshold = runtime.get("memory_similarity")
    if features is None or threshold is None:
        note = "past designs need the state's case and the memory_similarity setting"
        return {"experience": [], "note": note, **found}
    entries = from_store("search_memory", search_experience, memory, features, threshold)
    return {"experience": entries[:SHOWN_ENTRIES], "threshold": threshold, **found}


CURATOR = "curator"
"""The role that writes lessons for every role, so it reads them all."""


def memory_lessons(memory):
    """Return every lesson and user fact of the memory, of every role, in order."""
    return [
        entry
        for entry in memory.entries("experience")
        if entry.get("kind") in ("lesson", "user_fact")
    ]


MULTI_WORD = ("lead", "engineer")
"""The endings of the role settings of agents whose names have more than one word."""


def is_role(role):
    """Tell whether ``role`` is an agent's snake name, such as ``design_lead``, or ``all``.

    The role settings name each agent without underscores (``designlead``); a role of more than
    one word must have them, so ``designlead`` is no role.
    """
    if role == "all":
        return True
    joined = role.replace("_", "")
    one_word = "_" not in role and not joined.endswith(MULTI_WORD)
    snake = role == role.lower() and (one_word or "_" in role)
    return snake and joined in runtime.ROLES


def role_of(context):
    """Return the snake name of the agent that makes the call, or ``None``."""
    agent = getattr(context.session, "agent", None)
    return getattr(agent, "name", None)


@tool(effect="read")
def read_memory(context, id: str):
    """Return one experience entry by the id ``search_memory`` gave. Skill `memory`."""
    memory = memory_of(context, "read_memory")
    for entry in from_store("read_memory", memory.entries, "experience"):
        if entry.get("id") == id:
            return entry
    raise ToolError(
        f"read_memory: experience has no entry {id!r}; expected an id that search_memory gave",
        code="unknown_name",
        path="id",
    )


MOST_LESSONS = 3
"""The most entries one run keeps (QA-199: eight or nine lessons a run, each its own card)."""


class Lesson(BaseModel):
    """One entry of the memory's experience: a lesson for a role, or a fact the user stated."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["lesson", "user_fact"]
    role: str
    text: str
    source: str


FLAT_FIELDS = ("id", "kind", "role", "text", "source")
"""The fields of the older one-entry form of ``write_lesson``, still accepted (no API break)."""


def given_entries(lessons, flat):
    """Return the entries of a call: its ``lessons`` list, or the older one-entry form.

    The API stays additive: the five fields of one entry are still accepted beside the list,
    never both in one call.
    """
    given = {name: value for name, value in flat.items() if value is not None}
    if lessons is not None and given:
        raise ToolError(
            f"write_lesson: lessons and {', '.join(given)} given; expected the lessons list alone",
            code="invalid_input",
            path="lessons",
        )
    if lessons is not None:
        return [lesson if isinstance(lesson, dict) else lesson.model_dump() for lesson in lessons]
    if not given:
        return []
    missing = [name for name in FLAT_FIELDS if name not in given]
    if missing:
        raise ToolError(
            f"write_lesson: {', '.join(missing)} missing; expected lessons = [{{id, kind, role, "
            "text, source}, ...]",
            code="invalid_input",
            path=missing[0],
        )
    return [Lesson.model_validate(given).model_dump()]


def check_roles(entries):
    """Raise unless each entry's role is an agent's snake name or ``all``."""
    for index, entry in enumerate(entries):
        if not is_role(entry["role"]):
            raise ToolError(
                f"write_lesson: role = {entry['role']!r}; expected an agent's snake name, such "
                "as design_lead, or all",
                code="unknown_name",
                path=f"lessons.{index}.role",
                suggestions=difflib.get_close_matches(
                    entry["role"].replace("_", ""), runtime.ROLES
                ),
            )


@tool(effect="write", idempotent=True)
def write_lesson(
    context,
    lessons: list[Lesson] | None = None,
    id: str | None = None,
    kind: Literal["lesson", "user_fact"] | None = None,
    role: str | None = None,
    text: str | None = None,
    source: str | None = None,
):
    """Keep the run's general lessons for roles, and the facts the user gave, in one call.

    One call holds every entry of the run, so the user approves them on one card (QA-199).
    Skill `memory`.
    """
    memory = memory_of(context, "write_lesson")
    flat = {"id": id, "kind": kind, "role": role, "text": text, "source": source}
    entries = given_entries(lessons, flat)
    if not entries:
        raise ToolError(
            "write_lesson: lessons = []; expected at least one entry, or keep nothing and finish",
            path="lessons",
        )
    if len(entries) > MOST_LESSONS:
        raise ToolError(
            f"write_lesson: {len(entries)} entries; expected at most {MOST_LESSONS} a run: keep "
            "only the ones a refused call, a reviewer finding or a user correction taught",
            code="invalid_input",
            path="lessons",
        )
    check_roles(entries)
    origin = {"run": context.session.state.run_id}
    checked = [
        checked_lesson(
            {
                "id": entry["id"],
                "kind": entry["kind"],
                "role": entry["role"],
                "text": entry["text"],
                "origin": {**origin, "source": entry["source"]},
                "project_id": context.project,
            }
        )
        for entry in entries
    ]
    for entry in checked:
        from_store("write_lesson", memory.add, "experience", entry)
    return {"written": [entry["id"] for entry in checked]}


SAME_TEXT = 0.8
"""How alike two lesson texts are, at least, to be the same lesson under another id or role."""


def _words(text):
    """Return a lesson's text in lower case with its spacing made single, for comparing."""
    return " ".join(str(text or "").lower().split())


def lessons_of(tool_input):
    """Return the entries of a ``write_lesson`` call's input, an older single entry as one."""
    item = tool_input or {}
    if isinstance(item.get("lessons"), list):
        return [entry for entry in item["lessons"] if isinstance(entry, dict)]
    return [item] if item.get("text") else []


def denied_lessons(events):
    """Return the lessons the user denied in this request: one card's, or the ones their words name.

    QA-265: a denied lesson came back under another id and role ``all``. A card of one entry
    denied is that entry; a card of several denied with words is the entries whose id the words
    name (the other entries may come back without them); a denial without words stops the tool.
    """
    inputs, denied = {}, []
    for event in events:
        call = getattr(event, "call", None)
        if event.type == "request" and call is not None:
            inputs[call.id] = call.input
        if not (
            event.type == "permission"
            and event.decision == "deny"
            and event.rule == "user"
            and event.tool == "write_lesson"
        ):
            continue
        entries = lessons_of(inputs.get(getattr(event, "call_id", None)))
        words = _words(event.reason)
        named = [entry for entry in entries if _words(entry.get("id")) in words]
        denied += entries if len(entries) == 1 else named
    return denied


def repeated_denial(events, tool_input):
    """Return the refusal of a ``write_lesson`` call that holds a lesson denied before, or None.

    A lesson is the same when its id is, or its text is at least ``SAME_TEXT`` alike, whatever
    its role.
    """
    denied = denied_lessons(events)
    if not denied:
        return None
    again = []
    for entry in lessons_of(tool_input):
        text = _words(entry.get("text"))
        for earlier in denied:
            ratio = difflib.SequenceMatcher(None, text, _words(earlier.get("text"))).ratio()
            if entry.get("id") == earlier.get("id") or ratio >= SAME_TEXT:
                again.append(f"{entry.get('id')} (the denied {earlier.get('id')})")
                break
    if not again:
        return None
    return (
        "write_lesson: the user denied these lessons earlier in this request, so they are never "
        f"written, under any id or role: {', '.join(again)}; leave them out, and call "
        "write_lesson again only with the other entries, or finish"
    )


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

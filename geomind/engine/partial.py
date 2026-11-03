"""The answer of a run that a limit stopped: built from its record, with no LLM call."""

import asyncio

from geomind import runtime
from geomind.errors import GeomindError
from geomind.verify.design import verify_design

SHORT = 300


def is_limit_stop(session, stop):
    """Tell whether a root run stopped on a budget, step or time limit and can answer by rule."""
    if session.state.parent is not None or session.agent.output.kind is not str:
        return False
    return stop.reason == "step_limit" or (stop.reason == "denied" and session.limit_reached)


def _cut(text):
    """Return a text cut at ``SHORT`` characters."""
    return text if len(text) <= SHORT else f"{text[:SHORT]}..."


def _asked(state):
    """Return what was asked: the goal of the problem state, else the first user message."""
    if state.problem.goal:
        return state.problem.goal
    return next((item.content for item in state.messages if item.role == "user"), "")


def _designs(problem):
    """Return the design lines of the problem state."""
    design = problem.design or {}
    reference = design.get("reference")
    lines = [f"design {reference}"] if reference else []
    return [*lines, *map(_alternative, _judged(design))]


def _judged(design):
    """Return the alternatives of a comparison, which have a verdict."""
    return [item for item in design.get("alternatives") or () if item.get("verdict")]


def _alternative(item):
    """Return the line of one alternative."""
    reason = f": {_cut(item['reason'])}" if item.get("reason") else ""
    return f"alternative {item.get('family')}, {item['verdict']}{reason}"


def _studies(events):
    """Return one line per study the log recorded."""
    lines = []
    for event in events:
        if event.type == "study.recorded":
            best = f", best {event.best}" if event.best else ""
            lines.append(f"{event.study} ({event.tool}, designs {', '.join(event.designs)}{best})")
    return lines


def _results(problem):
    """Return one line per result with its reference."""
    return [
        f"{item.id}: {_cut(item.summary)}" + (f" ({item.reference})" if item.reference else "")
        for item in problem.results
    ]


def _checks_line(found):
    """Return the line about gemini's checks of the design."""
    if found["passed"]:
        return f"all {len(found['checks'])} checks passed"
    failed = ", ".join(f"{item['name']} ({item['domain']})" for item in found["failures"])
    return f"failed: {failed}"


async def _checks(session, problem):
    """Return gemini's verdict on the design as a line, or ``None`` when nothing is verifiable."""
    if not (problem.design or {}).get("reference"):
        return None
    if not (problem.verification or {}).get("result"):
        return "not run: the design has no verification result yet"
    try:
        found = await runtime.in_gemini_thread(verify_design, session.context())
    except (GeomindError, OSError, ValueError) as error:
        return f"could not be run again: {_cut(str(error))}"
    return _checks_line(found)


def _open_items(problem):
    """Return the open questions and the unconfirmed assumptions."""
    questions = [f"{item.id}: {_cut(item.text)}" for item in problem.questions]
    unconfirmed = [item for item in problem.assumptions if not item.confirmed]
    assumed = [f"{item.id}: {_cut(item.text)}" for item in unconfirmed]
    return questions, assumed


def next_step(problem):
    """Return what a rerun with a higher cap does next, from the problem state."""
    if problem.questions:
        return "ask the user the open questions"
    if problem.case is None:
        return "set the case, then design"
    if not (problem.design or {}).get("reference"):
        return "design and size a plant for the case"
    if not (problem.verification or {}).get("result"):
        return "simulate the design and check it against the requirements"
    return "continue from the stored design and result, then explain them to the user"


def _section(title, lines):
    """Return a titled list, or nothing when the list is empty."""
    return [f"{title}:", *(f"- {line}" for line in lines)] if lines else []


async def partial_answer(session, stop):
    """Return the text a limit stop answers with: the record of the run, with no model call.

    It says what was asked, the designs, studies and results with their references, the checks,
    the open questions and unconfirmed assumptions, why the run stopped and what a rerun with a
    higher limit does next. It reads the problem state and the log only.
    """
    state = session.state
    problem = state.problem
    events = await asyncio.to_thread(session.engine.store.load_events, state.root)
    questions, assumed = _open_items(problem)
    checks = await _checks(session, problem)
    lines = [
        "The run stopped before it finished, so this is a partial answer built from its record; "
        "no model wrote it.",
        f"Asked: {_cut(_asked(state))}",
        *_section("Designs", _designs(problem)),
        *_section("Studies", _studies(events)),
        *_section("Results", _results(problem)),
        *([f"Checks: {checks}"] if checks else []),
        *_section("Open questions", questions),
        *_section("Unconfirmed assumptions", assumed),
        f"Why it stopped: {stop.message or stop.reason}",
        f"A rerun with a higher limit would: {next_step(problem)}.",
    ]
    return "\n".join(lines)

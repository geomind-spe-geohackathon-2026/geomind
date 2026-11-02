"""gemini's example projects: where they are and what they hold, for tests that read a case.

The published gemini wheel ships no examples, so ``gemini_examples/`` holds a copy of the two
projects from gemini's tag v0.5.5 (without their README and PDF).
"""

import copy
import json
from functools import cache
from pathlib import Path

import pytest

from geomind.stores.casefiles import named_files

EXAMPLES = ("hackathon_2026", "shallow_district")
SHALLOW_PEAK_HEATING = 3.034e6
"""The heating peak of ``shallow_district``, in W: its CSV is in kW."""
PLANTS = {"hackathon_2026": "HackathonPlant", "shallow_district": "HeatingHeatPumpCoolingPlant"}
"""The plant file of each example that the tests simulate."""


def example_folder(name):
    """Return the folder of one of gemini's example projects."""
    return Path(__file__).parent / "gemini_examples" / name


@cache
def read_example(name):
    """Return ``(case.json text, {file name: bytes})`` of an example, read once."""
    folder = example_folder(name)
    text = (folder / "case.json").read_text()
    files = named_files(
        json.loads(text),
        lambda file: (folder / file).read_bytes() if (folder / file).is_file() else None,
    )
    return text, files


def example_case(name):
    """Return ``(case dict, {file name: bytes})`` of an example: its series and economics.json."""
    text, files = read_example(name)
    return json.loads(text), copy.copy(files)


@cache
def read_plants(name):
    """Return ``{plants/<file>: bytes}`` of the plant files of an example."""
    folder = example_folder(name)
    return {
        f"plants/{path.name}": path.read_bytes()
        for path in sorted((folder / "plants").glob("*.json"))
    }


def example_plant_files(name):
    """Return ``{plants/<file>: bytes}`` of the plant files of an example."""
    return copy.copy(read_plants(name))


def example_plant(name, plant=None):
    """Return a new gemini plant of an example: ``plant`` names a file in ``plants/``."""
    import gemini as gm

    file = f"plants/{plant or PLANTS[name]}.json"
    return gm.Plant.from_dict(json.loads(read_plants(name)[file]))


example_names = pytest.mark.parametrize("name", EXAMPLES)


def warm_gemini():
    """Import gemini and build both examples once, so no timed test call pays for the import."""
    import gemini as gm

    for name in EXAMPLES:
        data, files = example_case(name)
        gm.Case.from_dict(data, files=files)


async def case_context(name, session=None, project=None):
    """Return a tool context whose state holds an example's case, its files stored in the run."""
    from geomind.context import ProblemState
    from geomind.engine import Context
    from tests.fixtures.sessions import StubSession

    session = session or StubSession()
    data, files = example_case(name)
    for file, content in files.items():
        await session.save_artifact(f"case/{file}", content)
    return Context(session=session, problem=ProblemState(case=data), project=project)


async def engine_context(name, project=None):
    """Return ``(context, events)``: a case context over a real session, with the run's event list.

    NOTE: the session is the engine's own, so a design is write-once and an event is saved before
    anything acts on it, as in a run; ``events`` fills as the tools emit.
    """
    from geomind.engine.log import RunLog
    from geomind.engine.session import RunSession
    from geomind.engine.state import RunState
    from tests.fixtures.runs import Worker, engine_for

    engine = engine_for([])
    log = RunLog(engine, "r1")
    state = RunState(root="r1", run_id="r1", chat="chat", agent="worker")
    session = RunSession(engine, log, state, Worker())
    context = await case_context(name, session=session, project=project)
    state.problem = context.problem
    return context, engine.store.events.setdefault("r1", [])

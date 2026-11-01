"""gemini's example cases: where they are and what they hold, for tests that read a case."""

import json
from pathlib import Path

import pytest

EXAMPLES = ("hackathon_2026", "shallow_district")
SHALLOW_PEAK_HEATING = 3.034e6
"""The heating peak of ``shallow_district``, in W: its CSV is in kW."""


def example_folder(name):
    """Return the folder of one of gemini's example cases."""
    import gemini as gm

    return Path(gm.__file__).resolve().parents[1] / "inputs/examples" / name


def example_case(name):
    """Return ``(case dict, folder)`` of an example, the dict as its ``case.json`` holds it."""
    folder = example_folder(name)
    return json.loads((folder / "case.json").read_text()), folder


example_names = pytest.mark.parametrize("name", EXAMPLES)


PLANTS = {"hackathon_2026": "plants/HackathonPlant.json", "shallow_district": "plant.json"}
"""The plant of each example that passes its case; the hackathon one was found by hand."""


def example_plant(name, plant=None):
    """Return a new gemini plant of an example: ``plant`` names a file, else the passing one."""
    import gemini as gm

    return gm.Plant.from_json(example_folder(name) / (plant or PLANTS[name]))


async def case_context(name, session=None, project=None):
    """Return a tool context whose state holds an example's case, its files stored in the run."""
    from geomind.context import ProblemState
    from geomind.engine import Context
    from tests.fixtures.sessions import StubSession

    session = session or StubSession()
    data, folder = example_case(name)
    for file in (data.get("demand") or {}).get("file", "").split():
        await session.save_artifact(f"case/{file}", (folder / file).read_bytes())
    problem = ProblemState(case=data)
    return Context(session=session, problem=problem, project=project)

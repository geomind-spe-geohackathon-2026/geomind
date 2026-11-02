"""The case tools: set_case, read_case and save_profile, on gemini's two example projects."""

import copy
import json

import pytest

from geomind.context import ProblemState
from geomind.context.state import apply_changes
from geomind.engine import Context
from geomind.errors import ToolError
from geomind.stores import MemoryWorkspace
from geomind.tools.gemini.case import (
    case_of,
    checked_name,
    file_contents,
    merge_patch,
    read_case,
    save_profile,
    set_case,
)
from tests.fixtures.calls import call
from tests.fixtures.cases import SHALLOW_PEAK_HEATING, example_case, example_names, warm_gemini
from tests.fixtures.sessions import StubSession


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Pay for the gemini import and the first case build outside the timed calls."""
    warm_gemini()


def project_session(name):
    """Return a session whose workspace holds an example project as project ``p``."""
    return StubSession(workspace=MemoryWorkspace(cases={"p": example_case(name)}))


def state_after(session, problem=None):
    """Return the problem state that the last recorded change of a session gives."""
    return apply_changes(problem or ProblemState(), session.changes[-1])


async def loaded(name):
    """Return ``(session, problem)`` after ``set_case(source="project")`` on an example."""
    session = project_session(name)
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.is_error is False, result.output
    return session, state_after(session)


async def edited(session, problem, arguments):
    """Return the result of ``set_case`` with ``arguments`` on the state's case."""
    return await call(set_case, arguments, session, problem=problem)


def test_merge_patch_follows_rfc_7386():
    """A null removes a key, an object merges, anything else replaces; the target stays."""
    target = {"a": {"b": 1, "c": 2}, "d": [1]}
    patch = {"a": {"b": None, "e": 3}, "d": [2]}
    assert merge_patch(target, patch) == {"a": {"c": 2, "e": 3}, "d": [2]}
    assert target == {"a": {"b": 1, "c": 2}, "d": [1]}
    assert merge_patch({"a": 1}, 5) == 5


@pytest.mark.parametrize("name", ["/etc/passwd", "../x.csv", "a/../../x", "a\\b", ""])
def test_an_unsafe_file_name_is_refused(name):
    """A case file is a relative path inside the case: nothing absolute, no ``..``."""
    with pytest.raises(ToolError, match="relative path"):
        checked_name(name)


def test_a_path_with_folders_is_a_file_name():
    """``data/demand.csv`` is what gemini's examples name."""
    assert checked_name("data/demand.csv") == "data/demand.csv"


@example_names
async def test_a_project_case_is_loaded_with_every_file_it_names(name):
    """The case reaches the state as given, its series and economics the run's case files."""
    session, problem = await loaded(name)
    assert problem.case == example_case(name)[0]
    assert set(example_case(name)[1]) == {"data/demand.csv", "economics.json"}
    for file, content in example_case(name)[1].items():
        assert session.artifacts[f"case/{file}"] == content


async def test_the_stored_case_reproduces_the_shallow_heating_peak():
    """The case as given keeps the kW of the file."""
    session, problem = await loaded("shallow_district")
    context = Context(session=session, problem=problem)
    assert case_of(context).demand.frame["heating_demand"].max() == SHALLOW_PEAK_HEATING


async def test_without_a_case_the_state_says_what_to_call():
    """There is no fallback case: the model is told to set one or ask the user."""
    context = Context(session=StubSession())
    with pytest.raises(ToolError, match="set_case.*ask_user"):
        case_of(context)


async def test_changes_merge_into_the_state_case():
    """A merge patch changes one value and keeps the rest."""
    session, problem = await loaded("shallow_district")
    changes = {"site": {"ground": {"gradient": {"value": 30, "unit": "K/km"}}}}
    result = await edited(session, problem, {"changes": changes})
    assert result.is_error is False, result.output
    ground = state_after(session, problem).case["site"]["ground"]
    assert ground["gradient"] == {"value": 30, "unit": "K/km"}
    assert ground["surface_temperature"] == {"value": 9, "unit": "degC"}


@pytest.mark.parametrize("key", ["requirements", "economics"])
async def test_changes_refuse_the_keys_with_their_own_argument(key):
    """``requirements`` and ``economics`` have an argument each, and the error says which."""
    session, problem = await loaded("shallow_district")
    before = len(session.changes)
    result = await edited(session, problem, {"changes": {key: None}})
    assert result.is_error is True
    assert f"the argument '{key}'" in result.output["error"]["message"]
    assert len(session.changes) == before


async def test_a_requirement_is_added_by_name():
    """One requirement is added without sending the list; the others stay."""
    session, problem = await loaded("hackathon_2026")
    new = {"on": "doublet", "quantity": "count", "min": 1, "max": 2}
    result = await edited(session, problem, {"requirements": {"few_doublets": new}})
    assert result.is_error is False, result.output
    found = state_after(session, problem).case["requirements"]
    assert found[-1] == {**new, "name": "few_doublets"}
    assert found[:-1] == problem.case["requirements"]


async def test_a_requirement_is_replaced_by_name_in_its_place():
    """A requirement of an existing name is replaced as a whole, at its position."""
    session, problem = await loaded("hackathon_2026")
    new = {"on": "doublet", "quantity": "count", "min": 1, "max": 2}
    await edited(session, problem, {"requirements": {"doublet_count": new}})
    found = state_after(session, problem).case["requirements"]
    old = problem.case["requirements"]
    position = [item["name"] for item in old].index("doublet_count")
    assert found[position] == {**new, "name": "doublet_count"}
    assert len(found) == len(old)


async def test_a_requirement_is_removed_by_a_null():
    """A null removes one requirement and keeps the rest in order."""
    session, problem = await loaded("hackathon_2026")
    await edited(session, problem, {"requirements": {"doublet_count": None}})
    names = [item["name"] for item in state_after(session, problem).case["requirements"]]
    expected = [item["name"] for item in problem.case["requirements"]]
    assert names == [name for name in expected if name != "doublet_count"]


async def test_an_unknown_requirement_cannot_be_removed():
    """The error lists the names the case has."""
    session, problem = await loaded("hackathon_2026")
    result = await edited(session, problem, {"requirements": {"doublet_cont": None}})
    assert result.is_error is True
    assert result.output["error"]["code"] == "unknown_name"
    assert "doublet_count" in result.output["error"]["message"]


async def test_a_rejected_requirement_stores_nothing():
    """The path and message of gemini come back, and the state and the files stay as they were."""
    session, problem = await loaded("hackathon_2026")
    before = (len(session.changes), dict(session.artifacts))
    bad = {"on": "doublet", "quantity": "count", "min": "many"}
    result = await edited(session, problem, {"requirements": {"bad": bad}})
    assert result.is_error is True
    assert result.output["error"]["path"].startswith("requirements[")
    assert "expected a number" in result.output["error"]["message"]
    assert (len(session.changes), session.artifacts) == before


async def test_economics_is_a_merge_patch_on_its_file_stored_as_a_new_content():
    """The case keeps its file name and the new content is the patched economics."""
    session, problem = await loaded("shallow_district")
    original = json.loads(session.artifacts["case/economics.json"])
    patch = {"analysis_period": {"value": 20, "unit": "yr"}}
    result = await edited(session, problem, {"economics": patch})
    assert result.is_error is False, result.output
    stored = json.loads(session.artifacts["case/economics.json"])
    assert stored == {**original, **patch}
    assert state_after(session, problem).case["economics"] == "economics.json"


async def test_a_rejected_economics_stores_nothing():
    """A unit gemini refuses leaves the old economics file in the run."""
    session, problem = await loaded("shallow_district")
    before = session.artifacts["case/economics.json"], len(session.changes)
    patch = {"analysis_period": {"value": 20, "unit": "m"}}
    result = await edited(session, problem, {"economics": patch})
    assert result.is_error is True
    assert "analysis_period" in result.output["error"]["message"]
    assert (session.artifacts["case/economics.json"], len(session.changes)) == before


async def test_a_case_without_state_is_built_from_changes():
    """With no case and no source, the changes make the first case; gemini says what is missing."""
    time = {"start": "2027-01-01", "end": "2027-01-05", "step": {"value": 1, "unit": "d"}}
    _, problem = await loaded("shallow_district")
    first = {key: problem.case[key] for key in ("format", "kind", "name", "site")} | {"time": time}
    session = StubSession()
    result = await call(set_case, {"changes": first}, session)
    assert result.is_error is False, result.output
    assert state_after(session).case == first


async def test_a_rejected_case_comes_back_with_gemini_s_path_and_message():
    """The model reads where the case is wrong, and nothing is stored."""
    session, problem = await loaded("shallow_district")
    before = len(session.changes)
    changes = {"site": {"ground": {"gradient": {"value": 30, "unit": "m"}}}}
    result = await edited(session, problem, {"changes": changes})
    assert result.is_error is True
    assert result.output["error"]["path"].startswith("site.ground.gradient")
    assert "gradient" in result.output["error"]["message"]
    assert len(session.changes) == before


async def test_a_series_file_the_run_lacks_is_a_rejected_case():
    """A changed file name that no case file holds is gemini's error on the series."""
    session, problem = await loaded("shallow_district")
    power = {"unit": "kW", "file": "data/gone.csv", "column": "heat_kw"}
    changes = {"demand": {"heating": {"power": power}}}
    result = await edited(session, problem, {"changes": changes})
    assert result.is_error is True
    assert result.output["error"]["path"].startswith("demand.heating.power")


async def test_an_unknown_source_is_refused():
    """Only ``project`` and ``origin`` are sources."""
    result = await call(set_case, {"source": "elsewhere"}, StubSession())
    assert result.is_error is True
    assert "project" in result.output["error"]["message"]


async def test_the_project_source_needs_a_project_case():
    """A project without a case says so."""
    session = StubSession(workspace=MemoryWorkspace())
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.is_error is True
    assert "no case" in result.output["error"]["message"]


@example_names
async def test_read_case_returns_the_case_a_section_the_economics_or_the_schema(name):
    """The whole case, one section, the economics content, or gemini's schemas."""
    _, problem = await loaded(name)
    session = StubSession()
    for file, content in example_case(name)[1].items():
        await session.save_artifact(f"case/{file}", content)
    whole = await call(read_case, {}, session, problem=problem)
    assert whole.output == example_case(name)[0]
    time = await call(read_case, {"section": "time"}, session, problem=problem)
    assert time.output == example_case(name)[0]["time"]
    economics = await call(read_case, {"section": "economics"}, session, problem=problem)
    assert economics.output == json.loads(example_case(name)[1]["economics.json"])
    schema = await call(read_case, {"section": "schema"}, session, problem=problem)
    assert schema.reference is not None
    full = session.artifacts[schema.reference]
    assert full["additionalProperties"] is False
    assert full["economics_schema"]["title"]


async def test_read_case_names_the_sections_of_a_wrong_one():
    """An unknown section lists the right ones."""
    _, problem = await loaded("shallow_district")
    result = await call(read_case, {"section": "demnd"}, problem=problem)
    assert result.is_error is True
    assert "demand" in result.output["error"]["message"]


DAILY = [float(day) for day in range(1, 31)]
PROFILE = {
    "name": "mine",
    "values": DAILY,
    "unit": "MW",
    "start": "2027-01-01",
    "step": {"value": 1, "unit": "d"},
    "service": "heating",
}


async def test_a_thirty_day_profile_is_one_call_and_the_case_builds():
    """The profile is a CSV, the power leaf points at it, and the time follows the profile."""
    session, problem = await loaded("hackathon_2026")
    changes_before = len(session.changes)
    result = await call(save_profile, PROFILE, session, problem=problem)
    assert result.is_error is False, result.output
    assert len(session.changes) == changes_before + 1
    new = state_after(session, problem)
    power = new.case["demand"]["heating"]["power"]
    assert power == {"unit": "MW", "file": "data/mine.csv", "column": "mine"}
    assert new.case["time"] == {
        "start": "2027-01-01T00:00:00Z",
        "end": "2027-01-31T00:00:00Z",
        "step": {"value": 1, "unit": "d"},
    }
    text = session.artifacts["case/data/mine.csv"].decode().splitlines()
    assert text[:2] == ["time,mine", "2027-01-01T00:00:00Z,1.0"]
    frame = case_of(Context(session=session, problem=new)).demand.frame
    assert frame["heating_demand"].tolist() == [value * 1e6 for value in DAILY]


async def test_a_profile_that_covers_the_time_keeps_it():
    """A year of values on a year of time leaves the case's time alone."""
    session, problem = await loaded("hackathon_2026")
    year = {**PROFILE, "values": [1.0] * 365}
    result = await call(save_profile, year, session, problem=problem)
    assert result.is_error is False, result.output
    assert state_after(session, problem).case["time"] == problem.case["time"]


async def test_save_profile_keeps_the_rest_of_the_demand():
    """The temperatures of the service and the other service stay."""
    session, problem = await loaded("hackathon_2026")
    result = await call(save_profile, {**PROFILE, "values": [1.0] * 365}, session, problem=problem)
    assert result.is_error is False, result.output
    demand = state_after(session, problem).case["demand"]
    given = problem.case["demand"]
    assert demand["cooling"] == given["cooling"]
    assert demand["heating"]["supply_temperature"] == given["heating"]["supply_temperature"]


async def test_save_profile_refuses_values_gemini_refuses():
    """A negative value is gemini's ``out_of_bounds``, and nothing is stored."""
    session, problem = await loaded("shallow_district")
    before = len(session.changes)
    result = await call(save_profile, {**PROFILE, "values": [-1.0]}, session, problem=problem)
    assert result.is_error is True
    assert result.output["error"]["code"] == "out_of_bounds"
    assert len(session.changes) == before


@pytest.mark.parametrize("unit", ["day", "hour"])
async def test_save_profile_with_a_step_unit_gemini_rejects_lists_the_durations(unit):
    """The error keeps gemini's message and lists the units gemini accepts for a duration."""
    import gemini as gm

    session, problem = await loaded("shallow_district")
    step = {"value": 1, "unit": unit}
    before = len(session.changes)
    result = await call(save_profile, {**PROFILE, "step": step}, session, problem=problem)
    error = result.output["error"]
    assert result.is_error is True
    assert error["code"] == "invalid_unit"
    assert f"unit = {unit!r}; expected a known unit" in error["message"]
    for accepted in gm.units.names("duration"):
        assert accepted in error["message"]
    assert len(session.changes) == before


async def test_save_profile_needs_a_case():
    """The time of the run comes from the case, so there must be one."""
    result = await call(save_profile, PROFILE, StubSession())
    assert result.is_error is True
    assert "set_case" in result.output["error"]["message"]


async def test_save_profile_has_no_default_for_an_engineering_value():
    """Every argument is required."""
    required = set(save_profile.input_schema["required"])
    assert required == {"name", "values", "unit", "start", "step", "service"}


async def test_a_file_the_project_lacks_is_named_in_the_error():
    """A missing series file is a result the model can act on, never an internal error."""
    data, files = example_case("shallow_district")
    files = {name: content for name, content in files.items() if name != "data/demand.csv"}
    session = StubSession(workspace=MemoryWorkspace(cases={"p": (data, files)}))
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.output["error"]["code"] == "unknown_name"
    assert "'data/demand.csv'" in result.output["error"]["message"]


async def test_a_project_case_naming_a_file_outside_it_is_refused():
    """A name with ``..`` is refused before anything is read."""
    data = copy.deepcopy(example_case("shallow_district")[0])
    data["demand"]["heating"]["power"]["file"] = "../secret.csv"
    files = {"economics.json": example_case("shallow_district")[1]["economics.json"]}
    session = StubSession(workspace=MemoryWorkspace(cases={"p": (data, files)}))
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.is_error is True
    assert "relative path" in result.output["error"]["message"]


async def test_an_empty_file_is_a_file():
    """An empty supplied file is used as given, not replaced by the run's older one."""
    session = StubSession()
    await session.save_artifact("case/data/demand.csv", b"old")
    context = Context(session=session)
    data = {"demand": {"heating": {"power": {"file": "data/demand.csv"}}}}
    assert file_contents(context, data, {"data/demand.csv": b""}) == {"data/demand.csv": b""}


async def test_save_profile_reads_the_case_files_off_the_event_loop(monkeypatch):
    """The artifact reads of save_profile run in a worker thread, not on the event loop."""
    import threading

    from geomind.tools.gemini import case as case_module

    threads = []
    reader = case_module.file_contents

    def watched(*arguments):
        threads.append(threading.current_thread())
        return reader(*arguments)

    monkeypatch.setattr(case_module, "file_contents", watched)
    session, problem = await loaded("hackathon_2026")
    threads.clear()
    result = await call(save_profile, PROFILE, session, problem=problem)
    assert result.is_error is False, result.output
    assert len(threads) >= 2
    assert threading.main_thread() not in threads

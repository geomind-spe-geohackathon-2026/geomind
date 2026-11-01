"""The case tools: set_case, read_case and save_profile, on gemini's two example cases."""

import json

import pytest

from geomind.context import ProblemState
from geomind.engine import Context
from geomind.errors import ToolError
from geomind.stores import MemoryWorkspace
from geomind.tools.gemini.case import case_of, merge_patch, read_case, save_profile, set_case
from tests.fixtures.calls import call
from tests.fixtures.cases import SHALLOW_PEAK_HEATING, example_case, example_names
from tests.fixtures.sessions import StubSession


def project_session(name):
    """Return a session whose workspace holds an example case as project ``p``."""
    return StubSession(workspace=MemoryWorkspace(cases={"p": example_case(name)}))


async def loaded(name):
    """Return ``(session, problem)`` after ``set_case(source="project")`` on an example."""
    session = project_session(name)
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.is_error is False
    return session, state_after(session)


def state_after(session):
    """Return the problem state that the last recorded change of a session gives."""
    change = session.changes[-1][0]
    assert (change["op"], change["path"]) == ("replace", "/case")
    return ProblemState(version=1, case=change["value"])


def test_merge_patch_follows_rfc_7386():
    """A null removes a key, an object merges, anything else replaces; the target stays."""
    target = {"a": {"b": 1, "c": 2}, "d": [1]}
    patch = {"a": {"b": None, "e": 3}, "d": [2]}
    assert merge_patch(target, patch) == {"a": {"c": 2, "e": 3}, "d": [2]}
    assert target == {"a": {"b": 1, "c": 2}, "d": [1]}
    assert merge_patch({"a": 1}, 5) == 5


@example_names
async def test_a_project_case_is_loaded_with_its_files(name):
    """The case reaches the state as given and its CSV file the run's case files."""
    session, problem = await loaded(name)
    assert problem.case == example_case(name)[0]
    assert "case/demand.csv" in session.artifacts
    assert isinstance(session.artifacts["case/demand.csv"], bytes)


async def test_the_stored_case_reproduces_the_shallow_heating_peak():
    """The ``to_dict`` of gemini loses the kW of the file; the case as given keeps it."""
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
    changes = {"environment": {"ground": {"gradient": {"value": 30, "unit": "K/km"}}}}
    result = await call(set_case, {"changes": changes}, session, problem=problem)
    assert result.is_error is False
    new = state_after(session).case
    assert new["environment"]["ground"]["gradient"] == {"value": 30, "unit": "K/km"}
    assert new["environment"]["ground"]["surface_temperature"] == {"value": 9, "unit": "degC"}


async def test_a_case_without_state_is_built_from_changes():
    """With no case and no source, the changes make the first case, and ``time`` is enough."""
    time = {"start": "2027-01-01", "end": "2027-01-05", "step": {"value": 1, "unit": "d"}}
    session = StubSession()
    result = await call(set_case, {"changes": {"time": time}}, session)
    assert result.is_error is False
    assert state_after(session).case == {"time": time}


async def test_a_rejected_case_comes_back_with_gemini_s_path_and_message():
    """The model reads where the case is wrong, and nothing is stored."""
    session, problem = await loaded("shallow_district")
    before = len(session.changes)
    changes = {"environment": {"ground": {"gradient": {"value": 30, "unit": "m"}}}}
    result = await call(set_case, {"changes": changes}, session, problem=problem)
    assert result.is_error is True
    assert result.output["error"]["code"] == "invalid_unit"
    assert result.output["error"]["path"].startswith("environment.ground.gradient")
    assert "gradient" in result.output["error"]["message"]
    assert len(session.changes) == before


async def test_a_demand_file_the_run_lacks_is_a_rejected_case():
    """A changed file name that no case file holds is gemini's error on ``demand.file``."""
    session, problem = await loaded("shallow_district")
    result = await call(
        set_case, {"changes": {"demand": {"file": "gone.csv"}}}, session, problem=problem
    )
    assert result.is_error is True
    assert result.output["error"]["path"] == "demand.file"


async def test_an_unknown_source_is_refused():
    """Only ``project`` is a source."""
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
async def test_read_case_returns_the_case_or_a_section(name):
    """The whole case, one section, or gemini's schema."""
    _, problem = await loaded(name)
    whole = await call(read_case, {}, problem=problem)
    assert whole.output == example_case(name)[0]
    time = await call(read_case, {"section": "time"}, problem=problem)
    assert time.output == example_case(name)[0]["time"]
    schema = await call(read_case, {"section": "schema"}, problem=problem)
    assert schema.output["additionalProperties"] is False


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
THIRTY_DAYS = {"start": "2027-01-01", "end": "2027-01-31", "step": {"value": 1, "unit": "d"}}


async def case_with_time():
    """Return ``(session, problem)`` for a case with only a thirty day ``time``."""
    session = StubSession()
    await call(set_case, {"changes": {"time": THIRTY_DAYS}}, session)
    return session, state_after(session)


async def test_save_profile_makes_a_demand_gemini_accepts():
    """The case keeps the user's values, converted by gemini to W on read."""
    session, problem = await case_with_time()
    result = await call(save_profile, PROFILE, session, problem=problem)
    assert result.is_error is False
    new = state_after(session)
    assert new.case["demand"] == {
        "file": "mine.csv",
        "time_column": "time",
        "heating": {"column": "mine", "unit": "MW"},
    }
    context = Context(session=session, problem=new)
    frame = case_of(context).demand.frame
    assert frame["heating_demand"].tolist() == [value * 1e6 for value in DAILY]


async def test_save_profile_keeps_the_other_service_and_its_temperatures():
    """A heating profile joins a cooling service that is already on the same steps."""
    session, problem = await case_with_time()
    await call(
        save_profile, {**PROFILE, "service": "cooling", "name": "cold"}, session, problem=problem
    )
    problem = state_after(session)
    cooling = {"supply_temperature": {"value": 10, "unit": "degC"}}
    problem = ProblemState(
        version=2, case=merge_patch(problem.case, {"demand": {"cooling": cooling}})
    )
    await call(save_profile, PROFILE, session, problem=problem)
    demand = state_after(session).case["demand"]
    assert demand["cooling"] == {"column": "cold", "unit": "W", **cooling}
    assert demand["heating"] == {"column": "mine", "unit": "MW"}
    context = Context(session=session, problem=state_after(session))
    frame = case_of(context).demand.frame
    assert frame["cooling_demand"].tolist() == [value * 1e6 for value in DAILY]


async def test_save_profile_refuses_values_gemini_refuses():
    """A negative value is gemini's ``out_of_bounds``, and nothing is stored."""
    session, problem = await case_with_time()
    before = len(session.changes)
    result = await call(save_profile, {**PROFILE, "values": [-1.0]}, session, problem=problem)
    assert result.is_error is True
    assert result.output["error"]["code"] == "out_of_bounds"
    assert len(session.changes) == before


async def test_save_profile_on_other_steps_than_the_case_is_gemini_s_error():
    """Thirty values on a case of ten days do not fit its time, and nothing is stored."""
    session = StubSession()
    time = {**THIRTY_DAYS, "end": "2027-01-11"}
    await call(set_case, {"changes": {"time": time}}, session)
    before = len(session.changes)
    result = await call(save_profile, PROFILE, session, problem=state_after(session))
    assert result.is_error is True
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
    assert json.dumps(save_profile.input_schema)


async def test_a_file_the_project_lacks_is_named_in_the_error(tmp_path):
    """A missing demand file is a result the model can act on, never an internal error."""
    data = example_case("shallow_district")[0]
    session = StubSession(workspace=MemoryWorkspace(cases={"p": (data, tmp_path)}))
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.output["error"]["code"] == "unknown_name"
    assert "'demand.csv'" in result.output["error"]["message"]


async def test_an_empty_file_is_a_file():
    """An empty supplied file is used as given, not replaced by the run's older one."""
    from geomind.tools.gemini.case import file_contents

    session = StubSession()
    await session.save_artifact("case/demand.csv", b"old")
    context = Context(session=session)
    data = {"demand": {"file": "demand.csv"}}
    assert file_contents(context, data, {"demand.csv": b""}) == {"demand.csv": b""}

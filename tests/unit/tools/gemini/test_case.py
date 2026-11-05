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


@pytest.mark.parametrize("unit", ["degC/km", "°C/km", "C/km"])
async def test_a_gradient_in_degrees_per_km_goes_to_gemini_as_given(unit):
    """A gradient in °C/km is gemini 0.6.3's (request 31): set_case maps and lists nothing."""
    session, problem = await loaded("shallow_district")
    changes = {"site": {"ground": {"gradient": {"value": 30, "unit": unit}}}}
    result = await edited(session, problem, {"changes": changes})
    assert result.is_error is False, result.output
    assert state_after(session, problem).case["site"]["ground"]["gradient"] == {
        "value": 30,
        "unit": unit,
    }
    assert "converted" not in result.output


async def test_a_gas_fraction_in_mol_percent_is_gemini_s_to_convert():
    """A gas in ``mol%`` is set as given (gemini 0.6.2, request 15); ``%`` is named ``mol%``."""
    session, problem = await loaded("shallow_district")
    gas = {"CH4": {"value": 92, "unit": "mol%"}, "CO2": {"value": 8, "unit": "%"}}
    changes = {"site": {"fluid": {"dissolved_gas": gas}}}
    result = await edited(session, problem, {"changes": changes})
    assert result.is_error is False, result.output
    fluid = state_after(session, problem).case["site"]["fluid"]
    assert fluid["dissolved_gas"] == {
        "CH4": {"value": 92, "unit": "mol%"},
        "CO2": {"value": 8, "unit": "mol%"},
    }
    (entry,) = result.output["converted"]
    assert entry["path"] == "site.fluid.dissolved_gas.CO2"
    assert entry["to"] == {"value": 8, "unit": "mol%"}
    assert gas["CO2"] == {"value": 8, "unit": "%"}


@pytest.mark.parametrize("h2s", [5, 0], ids=["sour", "zero"])
async def test_h2s_in_the_dissolved_gas_is_accepted_and_reaches_gemini_as_given(h2s):
    """B3: ``site.fluid.dissolved_gas.H2S``, even at 0 mol%, is set and read by gemini as given."""
    session, problem = await loaded("hackathon_2026")
    gas = {
        "CH4": {"value": 75 + 5 - h2s, "unit": "mol%"},
        "CO2": {"value": 20, "unit": "mol%"},
        "H2S": {"value": h2s, "unit": "mol%"},
    }
    changes = {"site": {"fluid": {"dissolved_gas": gas}}}
    result = await edited(session, problem, {"changes": changes})
    assert result.is_error is False, result.output
    after = state_after(session, problem)
    assert after.case["site"]["fluid"]["dissolved_gas"] == gas
    read = case_of(Context(session=session, problem=after)).to_dict()
    assert read["site"]["fluid"]["dissolved_gas"]["H2S"] == {"value": h2s, "unit": "mol%"}
    assert "converted" not in result.output


async def test_every_problem_of_a_case_comes_back_in_one_call():
    """Three wrong values come back in one answer (gemini 0.6.2 judges the whole case, 13).

    The answer names the count, each path and the accepted units by path; nothing is stored.
    """
    session, problem = await loaded("shallow_district")
    changes = {
        "site": {
            "ground": {"gradient": {"value": 30, "unit": "K/s"}},
            "fluid": {"density": {"value": 1030, "unit": "kg"}},
        },
        "demand": {"heating": {"supply_temperature": {"value": "hot", "unit": "degC"}}},
    }
    result = await edited(session, problem, {"changes": changes})
    error = result.output["error"]
    assert result.is_error and "problems at 3 paths" in error["message"]
    for path in ("site.ground.gradient.unit", "site.fluid.density.unit", "supply_temperature"):
        assert path in error["message"]
    assert "site.ground.gradient: accepted units: C/km, C/m, K/km, K/m, degC/km" in "".join(
        error["suggestions"]
    )
    assert "site.fluid.density: accepted units: g/m3, kg/m3, mg/l" in error["suggestions"]
    assert state_after(session, problem).case == problem.case


async def test_unit_names_as_sources_print_them_are_set_as_gemini_s_names():
    """#118: units as sources print them are set under gemini's names, the same numbers.

    ``kg/m³``, ``mPa·s``, ``Nm³/m³``, ``MWcool`` and ``m³/h``, each listed with "unit name".
    """
    session, problem = await loaded("shallow_district")
    fluid = {
        "density": {"value": 1030, "unit": "kg/m³"},
        "viscosity": {"value": 0.4, "unit": "mPa·s"},
        "gas_liquid_ratio": {"value": 0.8, "unit": "Nm³/m³"},
    }
    changes = {"site": {"fluid": fluid}, "demand": {"cooling": {"power": {"unit": "MWcool"}}}}
    flow = {"on": "doublet", "quantity": "production_flow", "over": "each", "max": 300}
    requirements = {"max_flow": {**flow, "unit": "m³/h"}}
    result = await edited(session, problem, {"changes": changes, "requirements": requirements})
    assert result.is_error is False, result.output
    case = state_after(session, problem).case
    assert case["site"]["fluid"]["density"] == {"value": 1030, "unit": "kg/m3"}
    assert case["site"]["fluid"]["viscosity"] == {"value": 0.4, "unit": "mPa.s"}
    assert case["demand"]["cooling"]["power"]["unit"] == "MW"
    assert [item["unit"] for item in case["requirements"] if item["name"] == "max_flow"] == ["m3/h"]
    converted = {entry["path"]: entry for entry in result.output["converted"]}
    assert set(converted) == {
        "site.fluid.density",
        "site.fluid.viscosity",
        "site.fluid.gas_liquid_ratio",
        "demand.cooling.power",
        "requirements.max_flow",
    }
    assert converted["site.fluid.gas_liquid_ratio"]["to"] == {"value": 0.8, "unit": "Nm3/m3"}
    assert {entry["reason"] for entry in converted.values()} == {"unit name"}


async def test_a_case_with_gemini_s_own_units_has_no_converted_list():
    """Nothing mapped, nothing listed: the result keeps its two keys."""
    session, problem = await loaded("shallow_district")
    changes = {"site": {"ground": {"gradient": {"value": 30, "unit": "K/km"}}}}
    result = await edited(session, problem, {"changes": changes})
    assert set(result.output) == {"case", "version", "version_is"}


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


async def test_an_efficiency_in_percent_with_no_unit_is_refused_with_its_fraction():
    """#130: nemotron set pump_efficiency min 70 max 70; gemini reads that as 70, not 0.7."""
    session, problem = await loaded("hackathon_2026")
    before = len(session.changes)
    recorded = {"on": "doublet", "quantity": "pump_efficiency", "min": 70, "max": 70}
    result = await edited(session, problem, {"requirements": {"pump_efficiency": recorded}})
    assert result.is_error is True
    error = result.output["error"]
    assert "a fraction 0-1: 0.7, not 70" in error["message"]
    assert error["path"].startswith("requirements[") and error["code"] == "out_of_bounds"
    assert len(session.changes) == before
    right = {**recorded, "min": 0.7, "max": 0.7}
    result = await edited(session, problem, {"requirements": {"pump_efficiency": right}})
    assert result.is_error is False, result.output


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


async def test_a_tool_without_a_case_says_no_case():
    """A chat with no case gets the stable code the app acts on, and the same message."""
    result = await call(read_case, {})
    assert result.output["error"]["code"] == "no_case"
    assert result.output["error"]["message"].startswith("case: the problem state has no case")


async def test_no_case_in_a_project_with_a_case_file_says_to_load_it():
    """A model read ``no_case`` as "the project has no case"; the error names the case file."""
    result = await call(read_case, {}, project_session("hackathon_2026"), project="p")
    error = result.output["error"]
    assert error["code"] == "no_case"
    assert "the project has a case file: set_case(source='project') loads it" in error["message"]


async def test_a_tool_on_an_incomplete_case_names_what_is_missing():
    """A case gemini cannot read for missing values keeps gemini's message and lists the paths."""
    data = {key: value for key, value in example_case("shallow_district")[0].items()}
    del data["time"]
    session = StubSession()
    for file, content in example_case("shallow_district")[1].items():
        await session.save_artifact(f"case/{file}", content)
    profile = {
        "name": "extra",
        "values": [1.0, 2.0],
        "unit": "MW",
        "start": "2027-01-01T00:00:00",
        "step": {"value": 1, "unit": "d"},
        "service": "heating",
    }
    result = await call(save_profile, profile, session=session, problem=ProblemState(case=data))
    error = result.output["error"]
    assert error["code"] == "case_incomplete"
    assert error["message"] == "time: time is missing"
    assert error["path"] == "time.start"
    assert error["suggestions"] == ["time.start", "time.end", "time.step"]


async def test_a_case_that_reads_but_is_wrong_keeps_gemini_s_error():
    """Only missing values are ``case_incomplete``; a bad value stays gemini's own code."""
    data = copy.deepcopy(example_case("shallow_district")[0])
    data["time"]["step"] = {"value": "x", "unit": "d"}
    session = StubSession()
    for file, content in example_case("shallow_district")[1].items():
        await session.save_artifact(f"case/{file}", content)
    profile = {
        "name": "extra",
        "values": [1.0, 2.0],
        "unit": "MW",
        "start": "2027-01-01T00:00:00",
        "step": {"value": 1, "unit": "d"},
        "service": "heating",
    }
    result = await call(save_profile, profile, session=session, problem=ProblemState(case=data))
    assert result.output["error"]["code"] != "case_incomplete"


DEMAND = b"time,heat_mw\n2030-01-01T00:00:00Z,5\n2030-01-02T00:00:00Z,6\n2030-01-03T00:00:00Z,7\n"
FROM_FILE = {
    "format": 1,
    "kind": "case",
    "name": "from_a_file",
    "time": {"start": "2030-01-01", "end": "2030-01-03", "step": {"value": 1, "unit": "d"}},
    "demand": {"heating": {"power": {"unit": "MW", "file": "demand.csv", "column": "heat_mw"}}},
}


def session_with_file():
    """Return a session whose project ``p`` holds one demand file."""
    session = StubSession()
    session.workspace = MemoryWorkspace(files={"p": {"demand.csv": DEMAND}})
    return session


async def test_set_case_takes_a_project_file_by_name():
    """The file's bytes reach gemini, and the run keeps them, so no number is retyped."""
    session = session_with_file()
    problem = ProblemState()
    tool_input = {"changes": FROM_FILE, "files": ["demand.csv"]}
    result = await call(set_case, tool_input, session, "p", problem)
    assert result.output["case"]["demand"]["heating"]["power"]["file"] == "demand.csv"
    assert session.artifacts["case/demand.csv"] == DEMAND


async def test_set_case_with_an_unknown_file_lists_the_project_s_files():
    """Nothing is stored, and the error teaches the name."""
    session = session_with_file()
    tool_input = {"changes": FROM_FILE, "files": ["demnad.csv"]}
    error = (await call(set_case, tool_input, session, "p")).output["error"]
    assert error["code"] == "unknown_name"
    assert error["suggestions"] == ["demand.csv"]


async def test_set_case_with_a_file_on_a_workspace_without_files_says_so():
    """A backend that has not added ``file`` gets the code, not a crash."""
    session = StubSession()
    session.workspace = MemoryWorkspace()
    del_files = type("Old", (), {"plants": lambda self, project: {}})
    session.workspace = del_files()
    tool_input = {"changes": FROM_FILE, "files": ["demand.csv"]}
    error = (await call(set_case, tool_input, session, "p")).output["error"]
    assert error["code"] == "files_unavailable"


async def test_set_case_on_a_partial_case_lists_every_gap():
    """A case with values missing comes back with all of them, for one question to the user."""
    changes = {key: FROM_FILE[key] for key in ("format", "kind", "name")}
    error = (await call(set_case, {"changes": changes})).output["error"]
    assert error["code"] == "case_incomplete"
    assert error["suggestions"] == ["time.start", "time.end", "time.step"]


async def test_a_case_that_lacks_what_a_plant_needs_is_incomplete():
    """A case that reads but misses a value of the run says so, with gemini's message and path."""
    import gemini as gm

    from geomind.tools.dispatch import error_output

    error = gm.errors.ValidationError(
        "site.fluid.density is missing; expected a value in the case (it has no default)",
        path="site.fluid.density",
        code="missing_value",
        problems=[{"path": "site.fluid.density", "code": "missing_value"}],
    )
    found = error_output(error)["error"]
    assert found["code"] == "case_incomplete"
    assert found["path"] == "site.fluid.density"
    assert found["suggestions"] == ["site.fluid.density"]
    assert found["message"].startswith("site.fluid.density is missing")


async def test_a_missing_search_range_stays_gemini_s_error():
    """A range belongs to the plant, so it is no gap of the case."""
    import gemini as gm

    from geomind.tools.dispatch import error_output

    error = gm.errors.ValidationError(
        "depth.range is missing",
        path="params.depth.range",
        code="missing_value",
        problems=[{"path": "params.depth.range", "code": "missing_value"}],
    )
    assert error_output(error)["error"]["code"] == "missing_value"


async def test_a_section_the_case_lacks_says_it_is_unset():
    """#107: a section the case has not set says so, not "did you mean 'about'?".

    QA-014: an unset section is an answer, not an error, so the chat shows no failed call.
    """
    session, problem = await loaded("hackathon_2026")
    data = {key: value for key, value in problem.case.items() if key != "about"}
    problem = problem.model_copy(update={"case": data})
    found = (await call(read_case, {"section": "about"}, session, "p", problem)).output
    assert found["unset"] is True and "the case does not set 'about' yet" in found["note"]


def test_set_case_takes_changes_sent_as_json_text():
    """A model sent ``changes`` as its JSON text twice and the run ended (#67)."""
    arguments = set_case.validate({"changes": '{"format": 1, "site": {"name": "a"}}'})
    assert arguments["changes"] == {"format": 1, "site": {"name": "a"}}


def files_project(name, folder=""):
    """Return a session whose project ``p`` holds an example's case among its files, in ``folder``.

    The backend's view: ``case.json`` and its files are project files (``files/case.json``), and
    the workspace has no case of its own (E2E-1).
    """
    data, files = example_case(name)
    held = {f"{folder}case.json": json.dumps(data).encode()}
    held |= {f"{folder}{file}": content for file, content in files.items()}
    return StubSession(workspace=MemoryWorkspace(files={"p": held}))


@pytest.mark.parametrize("folder", ["", "inputs/"])
async def test_a_case_json_among_the_project_files_is_the_project_case(folder):
    """E2E-1: the project had ``files/case.json`` and set_case(source='project') said no case.

    A ``case.json`` among the project's files is the project's case, its files named beside it.
    """
    session = files_project("shallow_district", folder)
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.is_error is False, result.output
    data, files = example_case("shallow_district")
    assert state_after(session).case == data
    assert session.artifacts["case/data/demand.csv"] == files["data/demand.csv"]


async def test_a_project_without_a_case_says_where_it_looked():
    """E2E-1: the refusal names where a project case is read from, so no file is retyped."""
    session = StubSession(workspace=MemoryWorkspace(files={"p": {"brief.pdf": b"%PDF"}}))
    result = await call(set_case, {"source": "project"}, session, project="p")
    message = result.output["error"]["message"]
    assert result.is_error and "case.json" in message and "list_files" in message


async def test_a_json_named_case_that_is_no_case_is_refused_with_its_kind():
    """A ``case.json`` among the files that is no gemini case is named as such, never loaded."""
    held = {"case.json": json.dumps({"kind": "plant", "name": "x"}).encode()}
    session = StubSession(workspace=MemoryWorkspace(files={"p": held}))
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.is_error and "'plant'" in result.output["error"]["message"]


async def test_a_new_case_takes_its_own_arguments_from_changes():
    """E2E-8: a first case with ``requirements``, ``files`` and ``columns`` inside ``changes``.

    The run spent two calls on "changes has 'requirements'" and "key 'files'"; on a case that has
    none of them yet, they are the arguments of the same name, so the call is set as it is.
    """
    session = session_with_file()
    requirements = [{"name": "few", "on": "doublet", "quantity": "count", "min": 1, "max": 2}]
    renamed = DEMAND.replace(b"time,", b"date,")
    session.workspace.project_files["p"]["demand.csv"] = renamed
    changes = {
        **FROM_FILE,
        "requirements": requirements,
        "files": ["demand.csv"],
        "columns": {"demand.csv": {"date": "time"}},
    }
    result = await call(set_case, {"changes": changes}, session, "p", ProblemState())
    assert result.is_error is False, result.output
    case = result.output["case"]
    assert case["requirements"] == requirements and "files" not in case and "columns" not in case
    assert session.artifacts["case/demand.csv"].startswith(b"time,")


async def test_a_fraction_out_of_bounds_comes_with_gemini_s_problems_in_one_call():
    """E2E-8: pump_efficiency 70 was refused only after gemini's two problems were fixed.

    Every problem of the call comes back at once: gemini's and the efficiency's.
    """
    session, problem = await loaded("hackathon_2026")
    changes = {"site": {"ground": {"gradient": {"value": 30, "unit": "K/s"}}}}
    recorded = {"on": "doublet", "quantity": "pump_efficiency", "min": 70, "max": 70}
    arguments = {"changes": changes, "requirements": {"pump_efficiency": recorded}}
    result = await edited(session, problem, arguments)
    message = result.output["error"]["message"]
    assert result.is_error and "problems at 2 paths" in message
    assert "site.ground.gradient.unit" in message and "0.7, not 70" in message


async def test_a_series_without_its_column_names_the_columns_of_its_file():
    """E2E-8: ``demand.heating.power.column = None`` came back with no suggestion of a column."""
    session = session_with_file()
    power = {"unit": "MW", "file": "demand.csv"}
    changes = {**FROM_FILE, "demand": {"heating": {"power": power}}}
    result = await call(set_case, {"changes": changes}, session, "p", ProblemState())
    assert result.is_error is True
    assert "demand.heating.power.column: a column of demand.csv: 'heat_mw'" in "".join(
        result.output["error"]["suggestions"]
    )


def test_a_reference_depth_moved_without_its_pressure_is_flagged():
    """QA-119: reference depth 2500 to 3000 m with 250 bar(g) kept."""
    from geomind.tools.gemini.case import moved_reference_depth

    reservoir = {"reference_depth": {"value": 2500, "unit": "m"}, "pressure": {"value": 250}}
    moved = {**reservoir, "reference_depth": {"value": 3000, "unit": "m"}}
    warning = moved_reference_depth({"site": {"reservoir": reservoir}}, {"site": {"reservoir": moved}})
    assert "params.depth" in warning and "pressure" in warning
    assert moved_reference_depth({"site": {"reservoir": reservoir}}, {"site": {"reservoir": reservoir}}) is None


def first_case_session(content=DEMAND):
    """Return a session whose project ``p`` holds one demand file and no case."""
    return StubSession(workspace=MemoryWorkspace(files={"p": {"demand.csv": content}}))


async def test_an_empty_unit_is_no_unit_and_is_listed():
    """QA-222: ``"unit": ""`` on a fraction was refused at every path; it is left out."""
    changes = copy.deepcopy(FROM_FILE)
    gas = {"CH4": {"value": 0.8, "unit": ""}, "CO2": {"value": 0.2}}
    changes["site"] = {"fluid": {"dissolved_gas": gas}}
    result = await call(set_case, {"changes": changes}, first_case_session(), "p")
    assert result.is_error is False, result.output
    assert result.output["case"]["site"]["fluid"]["dissolved_gas"]["CH4"] == {"value": 0.8}
    paths = [item["path"] for item in result.output["converted"]]
    assert "site.fluid.dissolved_gas.CH4.unit" in paths


async def test_a_date_column_is_the_time_column_without_columns():
    """QA-222: the full call dropped ``columns``; a first column named ``date`` is renamed."""
    content = DEMAND.replace(b"time,", b"date,", 1).replace(b"T00:00:00Z", b"")
    changes = {**FROM_FILE, "demand": copy.deepcopy(FROM_FILE["demand"])}
    changes["demand"]["heating"]["power"]["time_zone"] = "UTC"
    result = await call(set_case, {"changes": changes}, first_case_session(content), "p")
    assert result.is_error is False, result.output
    assert {"path": "file demand.csv", "to": {"value": "time", "unit": None}}.items() <= next(
        item for item in result.output["converted"] if item["path"] == "file demand.csv"
    ).items()


async def test_files_alone_keep_their_columns_for_the_full_call():
    """QA-200, QA-222: the refusal names each file's columns, and its ``columns`` are kept."""
    session = first_case_session(DEMAND.replace(b"time,", b"stamp,", 1))
    columns = {"demand.csv": {"stamp": "time"}}
    alone = await call(set_case, {"files": ["demand.csv"], "columns": columns}, session, "p")
    error = alone.output["error"]
    assert error["code"] == "case_incomplete" and "kept" in error["message"]
    assert any("heat_mw" in item for item in error["suggestions"])
    result = await call(set_case, {"changes": FROM_FILE}, session, "p")
    assert result.is_error is False, result.output


async def test_the_project_source_with_values_on_a_project_without_a_case_is_a_new_case():
    """QA-200, QA-222: ``source='project'`` came first in every run; with changes it sets them."""
    arguments = {"source": "project", "changes": FROM_FILE}
    result = await call(set_case, arguments, first_case_session(), "p")
    assert result.is_error is False, result.output
    assert "no case.json" in result.output["note_on_source"]


async def test_a_partial_first_case_is_named_as_one_not_an_older_shape():
    """QA-200: a patch after a refused full call was told "older shape"; nothing was stored."""
    changes = {"site": {"ground": {"gradient": {"value": 30, "unit": "K/km"}}}}
    error = (await call(set_case, {"changes": changes}, first_case_session(), "p")).output["error"]
    assert error["code"] == "case_incomplete"
    assert "no case is stored yet" in error["message"] and "older shape" not in error["message"]


FLOW = {"on": "doublet", "quantity": "production_flow", "over": "each", "when": "running"}


async def test_a_lone_min_and_a_lone_max_of_one_quantity_are_one_range():
    """QA-160: 50 to 300 m3/h came as two requirements; set_case keeps one with both ends."""
    session, problem = await loaded("shallow_district")
    requirements = {
        "production_flow_range": None,
        "min_stable_flow": {**FLOW, "min": 50, "unit": "m3/h"},
        "max_production_flow": {**FLOW, "max": 300, "unit": "m3/h"},
    }
    result = await edited(session, problem, {"requirements": requirements})
    assert result.is_error is False, result.output
    names = [item["name"] for item in result.output["case"]["requirements"]]
    assert "production_flow_range" in names and "min_stable_flow" not in names
    joined = result.output["case"]["requirements"][names.index("production_flow_range")]
    assert (joined["min"], joined["max"]) == (50, 300)


async def test_an_exact_ratio_on_each_step_asks_for_its_tolerance():
    """QA-203: reinjection min 1, max 1 fails on round-off; geomind sets no tolerance, it asks."""
    session, problem = await loaded("shallow_district")
    ratio = {"on": "doublet", "quantity": "reinjection_ratio", "over": "each", "min": 1, "max": 1}
    result = await edited(session, problem, {"requirements": {"reinjection": ratio}})
    assert result.is_error is False, result.output
    assert "reinjection" in result.output["check_requirements"]


async def test_read_case_says_when_the_project_s_saved_case_differs():
    """QA-284: a case saved by hand on the Case page reached no agent; read_case now says so."""
    session, problem = await loaded("shallow_district")
    same = await call(read_case, {"section": "site"}, session, "p", problem)
    assert "project_case" not in same.output
    saved, files = copy.deepcopy(example_case("shallow_district"))
    saved["site"]["ground"]["gradient"] = {"value": 35, "unit": "K/km"}
    session.workspace.cases["p"] = (saved, files)
    output = (await call(read_case, {"section": "site"}, session, "p", problem)).output
    assert output["chat_case"]["ground"]["gradient"]["value"] != 35
    paths = [item["path"] for item in output["project_case"]["differs"]]
    assert paths == ["site.ground.gradient"]
    assert "set_case(source='project')" in output["project_case"]["note"]


async def test_an_uncertainty_of_another_kind_replaces_the_old_one_whole():
    """QA-154: a uniform over the case's normal kept its ``std`` and gemini refused it."""
    session, problem = await loaded("hackathon_2026")
    uniform = {"kind": "uniform", "min": 0.02, "max": 0.08}
    patch = {"discount_rate": {"uncertainty": uniform}}
    result = await edited(session, problem, {"economics": patch})
    assert result.is_error is False, result.output
    stored = json.loads(session.artifacts["case/economics.json"])
    assert stored["discount_rate"]["uncertainty"] == uniform


async def test_economics_other_than_the_approved_values_are_refused():
    """QA-279: set_case wrote another value than the user approved with ask_economics."""
    from geomind.context.state import Assumption

    session, problem = await loaded("hackathon_2026")
    approved = Assumption(
        id="economics.discount_rate",
        text="approved",
        value={"value": 0.05},
        confirmed=True,
    )
    problem = problem.model_copy(update={"assumptions": [approved]})
    patch = {"discount_rate": {"value": 0.08}}
    error = (await edited(session, problem, {"economics": patch})).output["error"]
    assert "the user approved 0.05" in error["message"]
    result = await edited(session, problem, {"economics": {"discount_rate": {"value": 0.05}}})
    assert result.is_error is False, result.output


async def test_a_saved_connector_table_is_found_by_its_name_without_its_folder():
    """QA-301: data/air.csv saved by save_mcp_table was named air.csv: twelve "not found"."""
    session = first_case_session()
    air = b"time,t2m\n2030-01-01T00:00:00Z,5\n2030-01-02T00:00:00Z,6\n2030-01-03T00:00:00Z,7\n"
    session.artifacts["case/data/air.csv"] = air
    changes = copy.deepcopy(FROM_FILE)
    changes["site"] = {"air": {"temperature": {"file": "air.csv", "column": "t2m", "unit": "degC"}}}
    arguments = {"changes": changes, "files": ["demand.csv", "air.csv"]}
    result = await call(set_case, arguments, session, "p")
    assert result.is_error is False, result.output
    assert result.output["case"]["site"]["air"]["temperature"]["file"] == "data/air.csv"
    assert any(item["path"] == "site.air.temperature.file" for item in result.output["converted"])


async def test_a_case_that_leaves_out_an_approved_value_says_which():
    """QA-304: ``site.air.pressure = 101325 Pa`` was approved, then left out of the stored case."""
    from geomind.tools import dispatch
    from geomind.types import Message, ToolCall

    question = "Confirm:\n12. site.air.pressure = 101325 Pa | the brief | constant\n"
    asked = ToolCall(id="q1", name="ask_user", input={"question": question})
    messages = (
        Message(role="assistant", content="", tool_calls=[asked]),
        Message(role="tool", tool_call_id="q1", content="approve all"),
    )
    first = {"changes": FROM_FILE}
    context = Context(project="p", session=first_case_session(), messages=messages)
    result = await dispatch(set_case, ToolCall(id="c1", name="set_case", input=first), context)
    assert result.is_error is False, result.output
    assert "site.air.pressure = 101325 Pa" in result.output["check_approved"]
    stopped = (*messages[:1], Message(role="tool", tool_call_id="q1", content="stop"))
    context = Context(project="p", session=first_case_session(), messages=stopped)
    result = await dispatch(set_case, ToolCall(id="c1", name="set_case", input=first), context)
    assert "check_approved" not in result.output

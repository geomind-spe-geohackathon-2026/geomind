"""Stored designs and runs: what the gemini tools keep, read back as gemini objects."""

import io

import pytest

from geomind.errors import ToolError
from geomind.tools.gemini.stored import load_design, load_run, ran_case, save_design, save_run
from geomind.verify.design import result_off_case
from tests.fixtures.cases import (
    SHALLOW_PEAK_HEATING,
    case_context,
    example_case,
    example_plant,
)

DEMAND = "case/data/demand.csv"


@pytest.fixture(scope="module", autouse=True)
def shallow():
    """Return the shallow example's ``(plant, case, results)``, simulated once."""
    import gemini as gm

    data, files = example_case("shallow_district")
    plant = example_plant("shallow_district")
    case = gm.Case.from_dict(data, files=files)
    return plant, case, gm.simulate(plant, case)


def peak(case):
    """Return the heating peak of a case, in W."""
    return case.demand.frame["heating_demand"].max()


async def test_a_design_reads_back_with_its_inputs(shallow):
    """A stored design is the plant dict with its inputs; ``from_dict`` restores them."""
    context = await case_context("shallow_district")
    reference = await save_design(context, "start", shallow[0])
    loaded = load_design(context, reference, "test")
    assert reference == "design/start"
    assert loaded.to_dict(structure=True) == shallow[0].to_dict(structure=True)


async def test_a_run_rebuilds_the_case_from_its_kept_files(shallow):
    """The plant, the case it ran on (series and economics from the kept files), the results."""
    plant, case, results = shallow
    context = await case_context("shallow_district")
    reference = await save_run(context, plant, results, {"steps": 1}, {}, ran_case(context))
    loaded_plant, loaded_case, loaded_results = load_run(context, reference, "test")
    assert reference.startswith("result/")
    assert loaded_plant.to_dict(structure=True) == plant.to_dict(structure=True)
    assert peak(loaded_case) == pytest.approx(SHALLOW_PEAK_HEATING)
    assert loaded_case.economics.to_dict() == case.economics.to_dict()
    assert loaded_results.to_bytes() == results.to_bytes()


@pytest.mark.parametrize("reference", ["result/unknown", "design/x", "x"])
async def test_an_unknown_run_is_unknown_name(reference):
    """A reference that no run returned says so; the model can list what it has."""
    context = await case_context("shallow_district")
    with pytest.raises(ToolError) as raised:
        load_run(context, reference, "check_results")
    assert raised.value.code == "unknown_name"


async def test_a_design_name_with_a_folder_is_refused(shallow):
    """A design name is one name: no path."""
    context = await case_context("shallow_district")
    with pytest.raises(ToolError, match="name = 'a/b'"):
        await save_design(context, "a/b", shallow[0])


async def test_a_run_on_other_case_files_has_another_reference(shallow):
    """The same plant and case dict on another series file is another run."""
    plant, _, results = shallow
    context = await case_context("shallow_district")
    first = await save_run(context, plant, results, {}, {}, ran_case(context))
    await context.session.save_artifact(DEMAND, context.session.load_artifact(DEMAND) + b"\n")
    assert await save_run(context, plant, results, {}, {}, ran_case(context)) != first


async def test_a_run_on_another_economics_has_another_reference(shallow):
    """The economics file is part of the case a run is keyed on."""
    plant, _, results = shallow
    context = await case_context("shallow_district")
    first = await save_run(context, plant, results, {}, {}, ran_case(context))
    file = "case/economics.json"
    await context.session.save_artifact(file, context.session.load_artifact(file) + b"\n")
    assert await save_run(context, plant, results, {}, {}, ran_case(context)) != first


def halved(content):
    """Return the shallow demand CSV with every heating value halved."""
    import pandas as pd

    frame = pd.read_csv(io.BytesIO(content))
    frame[frame.columns[1]] = frame[frame.columns[1]] / 2
    return frame.to_csv(index=False).encode()


async def test_an_older_run_keeps_the_files_it_ran_on(shallow):
    """Overwriting a case file under its name changes neither an older run nor its reference."""
    plant, _, results = shallow
    context = await case_context("shallow_district")
    reference = await save_run(context, plant, results, {}, {}, ran_case(context))
    await context.session.save_artifact(DEMAND, halved(context.session.load_artifact(DEMAND)))
    _, loaded_case, _ = load_run(context, reference, "test")
    assert peak(loaded_case) == pytest.approx(SHALLOW_PEAK_HEATING)


async def test_a_run_whose_case_file_changed_since_is_off_the_case(shallow):
    """Same case dict, new file content under the same name: the run is stale for verification."""
    plant, _, results = shallow
    context = await case_context("shallow_district")
    reference = await save_run(context, plant, results, {}, {}, ran_case(context))
    assert result_off_case(context, reference) is None
    await context.session.save_artifact(DEMAND, halved(context.session.load_artifact(DEMAND)))
    assert "another case" in result_off_case(context, reference)


async def test_a_run_whose_economics_changed_since_is_off_the_case(shallow):
    """A new economics file under the same name makes the run stale too."""
    plant, _, results = shallow
    context = await case_context("shallow_district")
    reference = await save_run(context, plant, results, {}, {}, ran_case(context))
    file = "case/economics.json"
    await context.session.save_artifact(file, context.session.load_artifact(file) + b"\n")
    assert "another case" in result_off_case(context, reference)


async def test_the_stored_case_is_the_one_the_run_read(shallow):
    """A case changed after the run read it (a parallel set_case) is not what the run stores."""
    from geomind.context import ProblemState

    plant, _, results = shallow
    context = await case_context("shallow_district")
    ran = ran_case(context)
    changed = {**context.problem.case, "requirements": []}
    context.problem = ProblemState(case=changed)
    reference = await save_run(context, plant, results, {}, {}, ran)
    stored = context.session.load_artifact(f"{reference.removeprefix('result/')}.case")
    assert stored == ran[0] != changed

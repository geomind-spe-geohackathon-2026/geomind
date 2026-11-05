"""The values gemini asks at later stages, named with the first issues (QA-175, QA-171)."""

import gemini
import pytest

import geomind as gd
from geomind.tools.gemini.stages import lacking_values
from tests.fixtures.calls import call
from tests.fixtures.cases import case_context
from tests.fixtures.sessions import StubSession

TOOLS = gd.tools.gemini
LATER = {
    "params.d0.depth",
    "params.d0.well_diameter",
    "params.d0.nominal_flow",
    "params.d0.pump_efficiency",
    "params.d0.nominal_wellhead_pressure",
    "params.heat_pump.temperature_setpoint",
    "params.peak_boiler.temperature_setpoint",
    "params.compression_chiller.temperature_setpoint",
    "params.compression_cooler.temperature_setpoint",
}
"""What a class plant lacks only at later stages of gemini's checks, with its case."""
new_gemini = pytest.mark.skipif(
    tuple(int(part) for part in gemini.__version__.split(".")[:3]) < (0, 6, 17),
    reason="gemini before 0.6.17 reads the setpoints in another schedule",
)


@new_gemini
async def test_a_class_plant_lists_the_values_of_every_stage_at_once():
    """The doublet's design values and the supply setpoints come with the first issues."""
    session = StubSession()
    context = await case_context("hackathon_2026", session)
    start = {
        "name": "p0",
        "plant": {"format": 1, "kind": "plant", "name": "p", "type": "HeatingHeatPumpCoolingPlant"},
    }
    found = await call(TOOLS.build_plant, start, session, problem=context.problem)
    paths = [issue["path"] for issue in found.output["issues"]]
    assert LATER <= set(paths)
    assert len(paths) == len(set(paths))
    case_values = {"params.d0.permeability", "params.d0.thickness"}
    assert not case_values & set(paths), "QA-212: the case fills them, no patch may"
    derived = {item["path"] for item in found.output.get("derived") or ()}
    assert "params.d0.esp.stage_count" in derived and not derived & set(paths)
    assert "params.injection_pump.pressure_setpoint" not in paths


async def test_without_a_case_no_setpoint_is_named():
    """A case may give the supply temperatures, so a plant alone names no setpoint."""
    session = StubSession()
    start = {
        "name": "p0",
        "plant": {"format": 1, "kind": "plant", "name": "p", "type": "HeatingPlant"},
    }
    found = await call(TOOLS.build_plant, start, session)
    assert not [i for i in found.output["issues"] if i["path"].endswith("temperature_setpoint")]


def test_a_probe_run_keeps_only_the_values_the_plant_lacks():
    """A probe run's refusal of a stand-in setpoint is no issue; a missing input is one."""
    issues = [
        {"path": "", "code": "invalid_binding", "message": "simulation inputs = a.frequency"},
        {"path": "x.flow", "code": "invalid_design", "message": "tear stream x has no first guess"},
        {"path": "hp.cop", "code": "invalid_design", "message": "lift too small at the setpoint"},
    ]
    assert [issue["path"] for issue in lacking_values(issues)] == ["", "x.flow"]


def test_the_doublet_design_names_agree_with_gemini():
    """geomind's copies of gemini's doublet design lists match gemini's (private) module."""
    from gemini.plants._utils import doublet_design

    from geomind.tools.gemini import stages

    assert stages.DOUBLET_COLUMN == doublet_design.COLUMN
    assert stages.DOUBLET_FLOW_PATH == doublet_design.FLOW_PATH
    assert stages.DOUBLET_PUMP == doublet_design.PUMP
    assert set(stages.DOUBLET_ESP) <= set(doublet_design.PUMP_VALUES)

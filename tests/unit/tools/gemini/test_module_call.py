"""What evaluate_module fixes and fills before gemini's call (IMP-012, IMP-013)."""

import pytest

from geomind.tools.gemini import module_call as fix
from geomind.tools.gemini.case import readable_case
from tests.fixtures.cases import example_case, example_plant


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


def test_evaluate_module_fixes_slips_of_form(gm):
    """IMP-012: a snake-case type and a control among the parameters are fixed, with notes."""
    kind, path, note = fix.module_type(gm, "heat_pump", None)
    assert (kind, path) == ("HeatPump", None) and "HeatPump" in note
    description = gm.modules.get("HeatPump")().describe()
    notes = []
    parameters, controls = fix.placed_inputs(
        description,
        {"mode": {"value": "heating"}, "temperature_setpoint": {"value": 70, "unit": "degC"}},
        {"capacity": {"value": 1, "unit": "MW", "range": {"min": 0, "max": 2}}},
        notes,
    )
    assert parameters == {"mode": "heating", "capacity": {"value": 1, "unit": "MW"}}
    assert controls == {"temperature_setpoint": {"value": 70, "unit": "degC"}}
    assert len(notes) == 4



def test_a_module_of_a_result_is_called_with_the_run_s_fluids_and_controls(gm, monkeypatch):
    """QA-269: heat_pump at a result's time gets each inlet's fluid and its scheduled setpoint."""
    from gemini.engine.apply import apply_case

    case = readable_case(*example_case("hackathon_2026"))
    plant = example_plant("hackathon_2026", "HeatingHeatPumpCoolingPlant")
    results = gm.simulate(plant, case, plan=gm.schedule(plant, case).iloc[:1])
    run = (plant, case, apply_case(plant, case))
    shown = plant.to_dict(structure=True, units="display")
    monkeypatch.setattr(fix, "plant_of", lambda *_: (shown, results, run))
    given = (None, None, None)
    kind, _, parameters, inlets, controls, notes = fix.prepared_call(
        None, "heat_pump", given, None, "result/x", "2027-01-01"
    )
    assert {port: "fluid" in stream for port, stream in inlets.items()} == {
        "source_in": True,
        "sink_in": True,
    }
    assert controls["temperature_setpoint"]["unit"] == "K"
    assert any("schedule" in note for note in notes)
    gm.call(gm.modules.get(kind), parameters, inlets, controls, units="display", on_error="raise")

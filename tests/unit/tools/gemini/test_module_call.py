"""What evaluate_module fixes and fills before gemini's call (IMP-012, IMP-013)."""

from geomind.tools.gemini import module_call as fix


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


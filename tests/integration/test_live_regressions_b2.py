"""Bugs of the design team's round B2, each from a recorded call (#76, #77)."""

import json
from pathlib import Path

from geomind.agents.design.process import ProcessEngineer
from geomind.tools.gemini import evaluate_module
from tests.fixtures.calls import call

CALLS = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "live" / "b2_evaluate_module.json").read_text()
)


async def test_a_control_given_as_a_parameter_says_where_it_goes():
    """#76: gemini raised a bare KeyError, seen as ``internal``; the engineer could not fix it."""
    error = (await call(evaluate_module, CALLS["control_as_parameter"])).output["error"]
    assert error["code"] == "invalid_input" and error["path"] == "parameters.temperature_setpoint"
    assert "give it in `controls`" in error["message"]


async def test_an_unknown_parameter_names_the_module_s_parameters():
    """A name the module has not is no internal error either."""
    tool_input = {"name": "HeatPump", "parameters": {"capasity": {"value": 1, "unit": "MW"}}}
    error = (await call(evaluate_module, tool_input)).output["error"]
    assert error["code"] == "invalid_input" and "capacity" in error["suggestions"]


def test_the_process_engineer_builds_from_the_project_plant():
    """#77: it built from ``read_plant(plant_class=...)``, a header with 110 values missing."""
    text = " ".join(ProcessEngineer().prompt.render().split())
    assert "A project plant (`read_plant(project_plant=...)`) holds every value" in text
    assert "gives only its header and modules" in text


async def test_a_call_without_its_stream_inlets_shows_their_form():
    """B2: the energy engineer called a heat pump without ``inlets`` seven times."""
    tool_input = {
        "name": "HeatPump",
        "parameters": {"capacity": {"value": 15, "unit": "MW"}},
        "controls": {"temperature_setpoint": {"value": 100, "unit": "degC"}},
    }
    error = (await call(evaluate_module, tool_input)).output["error"]
    assert error["code"] == "invalid_input" and "source_in, sink_in" in error["message"]
    assert '"m_dot"' in error["suggestions"][0] and "power_in" not in error["message"]

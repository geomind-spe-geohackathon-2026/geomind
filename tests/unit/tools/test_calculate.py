"""The calculator tool: sourced values combined, unit-checked and kept with an id."""

import pytest

from geomind.tools.calculate import calculate
from tests.fixtures.calls import call
from tests.fixtures.cases import case_context
from tests.fixtures.sessions import StubSession

SURFACE = {"case": "site.ground.surface_temperature"}
"""A sourced operand of the hackathon case: 12 degC."""


async def calculated(tool_input):
    """Return the result of one calculate call on the hackathon case, and the session."""
    session = StubSession()
    context = await case_context("hackathon_2026", session)
    return await call(calculate, tool_input, session, problem=context.problem), session


async def test_a_nested_operation_is_kept_as_its_own_calculation():
    """QA-235: [case value, {operation, operands, unit}] is one call; each node gets an id."""
    gradient = {
        "operation": "multiply",
        "operands": [{"number": 30, "unit": "K/km"}, {"number": 2.5, "unit": "km"}],
        "unit": "K",
    }
    tool_input = {
        "label": "reservoir temperature",
        "operation": "add",
        "operands": [SURFACE, gradient],
        "unit": "degC",
    }
    result, session = await calculated(tool_input)
    assert not result.is_error, result.output
    assert result.output["value"] == pytest.approx(87)
    kept = [change[0]["value"] for change in session.changes]
    assert len(kept) == 2 and kept[0]["value"] == pytest.approx(75)
    assert result.output["operands"][1]["source"]["id"] == kept[0]["id"]


async def test_value_and_unit_is_a_number():
    """QA-235: {value, unit}, the form of every other tool, reads as {number, unit}."""
    tool_input = {
        "label": "flow per doublet",
        "operation": "add",
        "operands": [SURFACE, {"value": 3, "unit": "K"}],
        "unit": "degC",
    }
    result, _ = await calculated(tool_input)
    assert not result.is_error, result.output
    assert result.output["value"] == pytest.approx(15)


async def test_numbers_alone_stay_refused_also_when_nested():
    """A tree of plain numbers has no source: refused as before."""
    nested = {"operation": "add", "operands": [{"number": 1, "unit": "K"}] * 2, "unit": "K"}
    tool_input = {
        "label": "x",
        "operation": "add",
        "operands": [{"number": 1, "unit": "K"}, nested],
        "unit": "K",
    }
    result, _ = await calculated(tool_input)
    assert result.is_error and "no operand has a source" in result.output["error"]["message"]


def test_qa_179_a_stored_path_ending_in_value_keeps_its_unit():
    """QA-179: lcts.value was read as dimensionless; the quantity lcts keeps its unit."""
    from geomind.tools.calculate import with_unit

    stored = {"metrics": {"lcts": {"value": 41.3, "unit": "EUR/MWh"}, "count": {"value": 3}}}
    assert with_unit(stored, "metrics.lcts.value", "operands[0]", "r") == "metrics.lcts"
    assert with_unit(stored, "metrics.lcts", "operands[0]", "r") == "metrics.lcts"
    assert with_unit(stored, "metrics.count.value", "operands[0]", "r") == "metrics.count.value"
    assert with_unit(stored, "metrics.none.value", "operands[0]", "r") == "metrics.none.value"

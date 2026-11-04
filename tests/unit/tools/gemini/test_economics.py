"""The economics question: written from the case lead's rows, and set by code on approve all."""

import json

import pytest

from geomind.errors import ToolError
from geomind.tools.gemini.economics import (
    EconomicsValue,
    approved_economics,
    ask_economics,
    economics_answered,
)
from geomind.types import Request
from tests.fixtures.calls import call
from tests.fixtures.cases import case_context

HEAT_PUMP = {
    "key": "capex.heat_pump",
    "value": 0.737864,
    "unit": "EUR/W",
    "row": "heat-pump-dea-2025-10mw",
    "source": "Technology Data for Generation of Electricity and District Heating, version 0019",
    "year": 2026,
    "status": "secondary",
    "url": "https://ens.dk/en/analyses-and-statistics/technology-data-generation-electricity-and-"
    "district-heating",
}
DRILLING = {
    "key": "capex.drilling",
    "value": 1844.74,
    "unit": "EUR/m",
    "row": "drilling-nl-2013-3000m",
    "source": "Mijnlieff et al. EGC 2013",
    "year": 2013,
    "status": "verified",
    "others": [
        {"row": "drilling-nl-2013-2300m", "value": 1246.83, "unit": "EUR/m"},
        {"row": "drilling-nl-2013-4000m", "value": 2075.37, "unit": "EUR/m"},
    ],
}
VALUES = [
    HEAT_PUMP,
    DRILLING,
    {"key": "currency", "value": "EUR", "source": "the catalogue's value_2015 columns"},
    {"key": "price_year", "value": 2015, "source": "the catalogue's value_2015 columns"},
    {"key": "discount_rate", "value": 0.05, "source": "the user's brief"},
]
"""Rows of the run's economics question (request-542), a single-row and a multi-row key."""


async def test_the_question_lists_every_value_with_its_row_and_the_others():
    """The required keys come first; a multi-row key shows the recommended row and the others."""
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    tool_input = {"values": VALUES, "open": ["capex.heat_exchanger"]}
    asked = ToolCall(id="q", name="ask_economics", input=tool_input)
    request = await dispatch(ask_economics, asked, Context(session=StubSession()))
    assert isinstance(request, Request)
    assert [option.value for option in request.options] == ["approve all", "change some", "stop"]
    lines = request.message.splitlines()
    assert lines.index("economics.currency = EUR | no row | the catalogue's value_2015 columns") < (
        lines.index(next(line for line in lines if line.startswith("economics.capex.heat_pump")))
    )
    drilling = next(line for line in lines if line.startswith("economics.capex.drilling"))
    assert "row drilling-nl-2013-3000m" in drilling
    assert "1246.83 EUR/m [drilling-nl-2013-2300m]" in drilling
    assert lines[-1] == "economics.capex.heat_exchanger"


async def test_a_question_without_the_currency_or_with_an_unknown_key_is_refused():
    """The run's question left currency, price year and discount rate as open lines of text."""
    result = await call(ask_economics, {"values": [HEAT_PUMP]})
    message = result.output["error"]["message"]
    assert result.is_error and "currency, price_year, discount_rate" in message
    wrong = [*VALUES, {"key": "capex.heatpump", "value": 1, "source": "x"}]
    result = await call(ask_economics, {"values": wrong})
    assert result.output["error"]["code"] == "unknown_name"


def test_the_approved_patch_holds_every_value_and_its_row():
    """Each key gets ``{value, unit}``; ``about.sources`` keeps each row id and source."""
    patch = approved_economics([EconomicsValue.model_validate(item) for item in VALUES])
    assert patch["capex"] == {
        "heat_pump": {"value": 0.737864, "unit": "EUR/W"},
        "drilling": {"value": 1844.74, "unit": "EUR/m"},
    }
    assert patch["currency"] == {"value": "EUR"} and patch["price_year"] == {"value": 2015}
    assert patch["about"]["sources"]["capex.drilling"]["row"] == "drilling-nl-2013-3000m"


async def test_approve_all_sets_every_value_and_records_each_row_as_an_assumption():
    """The run: approve all set only the single-row keys and kept no row ids; now code sets all."""
    context = await case_context("hackathon_2026")
    output = await economics_answered(context, {"values": VALUES}, "approve all")
    assert output["economics"] == "set"
    assert output["keys"][:2] == ["capex.heat_pump", "capex.drilling"]
    stored = json.loads(context.session.artifacts["case/economics.json"])
    assert stored["capex"]["drilling"]["value"] == 1844.74
    assert stored["currency"]["value"] == "EUR" and stored["price_year"]["value"] == 2015
    assert stored["discount_rate"]["value"] == 0.05
    assert stored["about"]["sources"]["capex.heat_pump"]["row"] == "heat-pump-dea-2025-10mw"
    [case_change, assumptions] = context.session.changes
    assert case_change[0]["path"] == "/case"
    recorded = {change["value"]["id"]: change["value"] for change in assumptions}
    assert set(recorded) == {f"economics.{item['key']}" for item in VALUES}
    drilling = recorded["economics.capex.drilling"]
    assert drilling["confirmed"] and drilling["citation"]["row"] == "drilling-nl-2013-3000m"
    assert drilling["citation"]["source"] == "Mijnlieff et al. EGC 2013"


async def test_another_answer_sets_nothing_and_typed_text_is_marked():
    """``change some`` comes back as it is; text that is no option is the user's typed answer."""
    context = await case_context("hackathon_2026")
    assert await economics_answered(context, {"values": VALUES}, "change some") == {
        "answer": "change some"
    }
    typed = await economics_answered(context, {"values": VALUES}, "drilling 2000 EUR/m")
    assert typed == {"answer": "drilling 2000 EUR/m", "typed": True}
    assert context.session.changes == []


async def test_a_value_gemini_refuses_is_an_error_the_model_reads():
    """A unit the key does not take comes back from set_case; nothing is recorded."""
    context = await case_context("hackathon_2026")
    wrong = [*VALUES[2:], {**HEAT_PUMP, "unit": "EUR/m3"}]
    with pytest.raises(ToolError):
        await economics_answered(context, {"values": wrong}, "approve all")
    assert context.session.changes == []

"""The economics question: written from the case lead's rows, and set by code on approve all."""

import json

import pytest

from geomind.errors import ToolError
from geomind.tools.gemini.economics import (
    TYPED_NOTE,
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
    currency = next(line for line in lines if line.startswith("economics.currency = EUR |"))
    assert lines.index(currency) < (
        lines.index(next(line for line in lines if line.startswith("economics.capex.heat_pump")))
    )
    drilling = next(line for line in lines if line.startswith("economics.capex.drilling"))
    assert "row drilling-nl-2013-3000m" in drilling
    assert "1246.83 EUR/m [drilling-nl-2013-2300m]" in drilling
    assert lines[-1] == "economics.capex.heat_exchanger"


async def test_a_question_without_the_currency_or_with_an_unknown_key_is_refused():
    """The run's question left currency, price year and discount rate as open lines of text."""
    result = await call(ask_economics, {"values": [{**HEAT_PUMP, "row": None}]})
    message = result.output["error"]["message"]
    assert result.is_error and "currency, price_year, discount_rate" in message
    result = await call(ask_economics, {"values": [HEAT_PUMP]})
    message = result.output["error"]["message"]
    assert result.is_error and message.startswith("ask_economics: discount_rate not named")
    wrong = [*VALUES, {"key": "capex.heatpump", "value": 1, "source": "x"}]
    result = await call(ask_economics, {"values": wrong})
    assert result.output["error"]["code"] == "unknown_name"
    assert "did you mean 'capex.heat_pump'" in result.output["error"]["message"]


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
    [assumptions, case_change] = context.session.changes
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
        "answer": "change some",
        "economics": "not set",
    }
    typed = await economics_answered(context, {"values": VALUES}, "drilling 2000 EUR/m")
    assert typed == {
        "answer": "drilling 2000 EUR/m",
        "economics": "not set",
        "typed": True,
        "note": TYPED_NOTE,
    }
    assert context.session.changes == []


async def test_a_value_gemini_refuses_is_an_error_the_model_reads():
    """A unit the key does not take comes back from set_case; nothing is recorded."""
    context = await case_context("hackathon_2026")
    wrong = [*VALUES[2:], {**HEAT_PUMP, "unit": "EUR/m3"}]
    with pytest.raises(ToolError):
        await economics_answered(context, {"values": wrong}, "approve all")
    assert context.session.changes == []


async def test_approve_all_on_a_case_without_economics_writes_the_header():
    """The run (seq 424): no economics file yet, approve all was refused as an older shape."""
    from geomind.context import ProblemState
    from geomind.engine import Context
    from tests.fixtures.cases import example_case
    from tests.fixtures.sessions import StubSession

    data, files = example_case("hackathon_2026")
    data.pop("economics")
    session = StubSession()
    for file, content in files.items():
        if file != "economics.json":
            await session.save_artifact(f"case/{file}", content)
    context = Context(session=session, problem=ProblemState(case=data))
    output = await economics_answered(context, {"values": VALUES}, "approve all")
    assert output["economics"] == "set"
    stored = json.loads(context.session.artifacts["case/economics.json"])
    assert (stored["format"], stored["kind"]) == (1, "economics")
    assert stored["name"].endswith("economics") and stored["currency"]["value"] == "EUR"


async def test_null_optional_fields_are_left_out_and_a_null_value_is_open():
    """The run: ``others: null`` (21 errors, seq 412), a key all null (seq 475); now accepted."""
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    currency = {
        "key": "currency",
        "value": "EUR",
        "unit": None,
        "row": None,
        "source": "knowledge/data-economics.csv",
        "url": None,
        "others": None,
    }
    open_key = dict.fromkeys(("value", "unit", "row", "source", "year", "url", "status"))
    values = [
        currency,
        {**HEAT_PUMP, "others": None},
        {**VALUES[3], "others": None},
        {**VALUES[4], "source": None, "row": "discount-rate-row"},
        {"key": "opex.fixed.heat_pump", **open_key},
    ]
    asked = ToolCall(id="q", name="ask_economics", input={"values": values, "open": None})
    request = await dispatch(ask_economics, asked, Context(session=StubSession()))
    assert isinstance(request, Request)
    assert request.message.splitlines()[-1] == "economics.opex.fixed.heat_pump"
    context = await case_context("hackathon_2026")
    output = await economics_answered(context, {"values": values}, "approve all")
    assert output["open"] == ["opex.fixed.heat_pump"]
    assert "opex.fixed.heat_pump" not in output["keys"]
    unsourced = [{**VALUES[2], "source": None}, *VALUES[3:]]
    result = await call(ask_economics, {"values": unsourced})
    assert result.is_error and "no row or source" in result.output["error"]["message"]


PBL = {"source": "PBL 5698", "status": "verified", "year": 2026}
ADDED = [
    {
        "key": "opex.per_energy.chp",
        "value": 5.4,
        "unit": "EUR/MWh",
        "row": "opex-variable-chp-gas-engine-dea-2018",
    },
    {
        "key": "revenue.subsidy.amount",
        "value": 48.699029126213595,
        "unit": "EUR/MWh",
        "row": "sde-basisbedrag-geothermal-pbl-2026-over-20mw",
        **PBL,
    },
    {
        "key": "revenue.subsidy.duration",
        "value": 15,
        "unit": "yr",
        "row": "sde-duration-geothermal-stcrt-2025",
    },
    {
        "key": "revenue.subsidy.cap",
        "value": 6000,
        "unit": "h/yr",
        "row": "sde-full-load-hours-geothermal-pbl-2026-over-20mw",
        **PBL,
    },
    {"key": "revenue.subsidy.capacity", "value": 20, "unit": "MW", "source": "the user"},
    {
        "key": "capex.ice_storage",
        "value": 23249.8663132687,
        "unit": "EUR/MWh",
        "row": "ice-storage-mlakar-2022-low",
    },
]
"""Rows of the economics parts gemini 0.6.2 added: per energy, the subsidy cap, ice storage."""


async def test_approve_all_sets_the_economics_parts_of_gemini_0_6_2():
    """``opex.per_energy``, the subsidy's ``cap`` in h/yr with its ``capacity``, ice storage.

    Their rows go in as any key's; gemini reads each with its unit (its schema since 0.6.2).
    """
    context = await case_context("hackathon_2026")
    output = await economics_answered(context, {"values": VALUES + ADDED}, "approve all")
    assert output["economics"] == "set", output
    stored = json.loads(context.session.artifacts["case/economics.json"])
    assert stored["opex"]["per_energy"]["chp"] == {"value": 5.4, "unit": "EUR/MWh"}
    assert stored["revenue"]["subsidy"]["cap"] == {"value": 6000, "unit": "h/yr"}
    assert stored["revenue"]["subsidy"]["capacity"] == {"value": 20, "unit": "MW"}
    assert stored["capex"]["ice_storage"]["unit"] == "EUR/MWh"


CATALOGUE_ROWS = [HEAT_PUMP, DRILLING, {"key": "discount_rate", "value": 0.051, "row": "dr-row"}]
"""Catalogue rows only: the currency and the price year are the catalogue's, never the model's."""


async def test_the_currency_and_price_year_follow_from_the_catalogue_s_columns():
    """E2E-9: the question left currency and price_year open though every value is EUR at 2015.

    A value from a catalogue row is its ``value_2015`` in ``unit_2015``: ask_economics shows EUR
    and 2015 with that source, never as open, and approve all sets and records both.
    """
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    tool_input = {"values": CATALOGUE_ROWS, "open": ["currency", "price_year"]}
    asked = ToolCall(id="q", name="ask_economics", input=tool_input)
    request = await dispatch(ask_economics, asked, Context(session=StubSession()))
    assert isinstance(request, Request), request
    lines = request.message.splitlines()
    assert "Open (no usable row; give a value with change some, or leave it open):" not in lines
    currency = next(line for line in lines if line.startswith("economics.currency = EUR |"))
    year = next(line for line in lines if line.startswith("economics.price_year = 2015 |"))
    assert "value_2015" in currency and "value_2015" in year
    context = await case_context("hackathon_2026")
    output = await economics_answered(context, tool_input, "approve all")
    stored = json.loads(context.session.artifacts["case/economics.json"])
    assert stored["currency"] == {"value": "EUR"} and stored["price_year"] == {"value": 2015}
    assert output["open"] == [] and {"currency", "price_year"} <= set(output["keys"])


async def test_another_currency_than_the_catalogue_s_is_refused():
    """A currency or price year other than the catalogue's says where they come from."""
    usd = [*CATALOGUE_ROWS, {"key": "currency", "value": "USD", "source": "x"}]
    result = await call(ask_economics, {"values": usd})
    message = result.output["error"]["message"]
    assert result.is_error and "value_2015" in message and "'EUR'" in message


async def test_a_key_with_a_value_and_in_open_is_named_with_what_to_do():
    """E2E-9: "keys = [...]; expected each key once" did not say the keys were in both lists."""
    result = await call(ask_economics, {"values": CATALOGUE_ROWS, "open": ["discount_rate"]})
    message = result.output["error"]["message"]
    assert result.is_error and "discount_rate is in values and in open" in message
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    nulls = [*CATALOGUE_ROWS[:2], {"key": "discount_rate", "value": None}]
    tool_input = {"values": nulls, "open": ["discount_rate"]}
    asked = ToolCall(id="q", name="ask_economics", input=tool_input)
    request = await dispatch(ask_economics, asked, Context(session=StubSession()))
    assert isinstance(request, Request)
    assert request.message.splitlines()[-1].endswith("discount_rate")


ICE = {
    "key": "capex.ice_storage",
    "value": 23249.8663132687,
    "unit": "EUR/MWh cold",
    "row": "ice-storage-mlakar-2022-low",
}
ESP = {
    "key": "capex.production_pump",
    "value": 0.5986231667165519,
    "unit": "EUR/W electric",
    "row": "production-pump-esp-kennisagenda-2016-500kwel",
}


async def test_a_row_s_basis_word_is_set_as_the_key_s_unit_and_shown_to_the_user():
    """E2E-10: ``EUR/MWh cold`` on ice storage was lost on approve all; ESP rows are per W electric.

    The unit before the basis word is one the key takes, so it is set (money per energy for ice
    storage); the question says the row's basis beside the key's, shaft power for the ESP.
    """
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    tool_input = {"values": [*CATALOGUE_ROWS, ICE, ESP]}
    asked = ToolCall(id="q", name="ask_economics", input=tool_input)
    request = await dispatch(ask_economics, asked, Context(session=StubSession()))
    assert isinstance(request, Request), request
    lines = request.message.splitlines()
    pump = next(line for line in lines if line.startswith("economics.capex.production_pump"))
    assert "EUR/W electric" in pump and "shaft power" in pump
    ice = next(line for line in lines if line.startswith("economics.capex.ice_storage"))
    assert "EUR/MWh cold" in ice and "energy capacity" in ice
    context = await case_context("hackathon_2026")
    output = await economics_answered(context, tool_input, "approve all")
    assert output["economics"] == "set", output
    stored = json.loads(context.session.artifacts["case/economics.json"])
    assert stored["capex"]["ice_storage"]["unit"] == "EUR/MWh"
    assert stored["capex"]["production_pump"]["unit"] == "EUR/W"


async def test_every_unit_a_key_refuses_is_named_before_the_user_is_asked():
    """E2E-10, E2E-8: a refused unit came back only after approve all, one key at a time.

    Each value whose unit its key does not take is named at once, with the units it takes.
    """
    waste = {
        "key": "opex.variable.waste_disposal",
        "value": 1027.221366204417,
        "unit": "EUR/m3",
        "row": "waste-disposal-tfa-france-2022",
    }
    wrong = [*CATALOGUE_ROWS, waste, {**ICE, "unit": "EUR/W"}]
    result = await call(ask_economics, {"values": wrong})
    message = result.output["error"]["message"]
    assert result.is_error and "2 values" in message
    assert "opex.variable.waste_disposal: unit 'EUR/m3'" in message and "EUR/kg" in message
    assert "capex.ice_storage: unit 'EUR/W'" in message and "EUR/MWh" in message


def test_the_catalogue_basis_is_what_the_catalogue_states():
    """The currency and price year ask_economics sets are the catalogue's columns and its notes."""
    import csv
    from pathlib import Path

    from geomind.tools.gemini.economics import CATALOGUE_BASIS

    folder = Path(__file__).parents[4] / "data" / "knowledge"
    year = CATALOGUE_BASIS["price_year"]
    header = next(csv.reader((folder / "data-economics.csv").open()))
    assert {f"value_{year}", f"unit_{year}"} <= set(header)
    notes = " ".join((folder / "data-economics.md").read_text().split())
    assert f"{CATALOGUE_BASIS['currency']} at {year} prices" in notes


async def test_a_row_given_as_the_catalogue_s_row_object_is_read_by_its_id():
    """E2E-14: ``row`` sent as the row object and ``others[]`` with ``year`` were 47 errors.

    The row's ``id`` is the row, and the object's citation fields fill those the value leaves out;
    another row of ``others`` takes the same citation fields.
    """
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    cited = {key: HEAT_PUMP[key] for key in ("source", "year", "url", "status")}
    heat_pump = {
        "key": HEAT_PUMP["key"],
        "value": HEAT_PUMP["value"],
        "unit": HEAT_PUMP["unit"],
        "row": {"id": HEAT_PUMP["row"], **cited},
    }
    other = {"row": "drilling-nl-2013-2300m", "value": 1246.83, "unit": "EUR/m", "year": 2013}
    drilling = {**DRILLING, "others": [{**other, "status": "verified", "url": "https://x"}]}
    tool_input = {"values": [heat_pump, drilling, VALUES[4]]}
    asked = ToolCall(id="q", name="ask_economics", input=tool_input)
    request = await dispatch(ask_economics, asked, Context(session=StubSession()))
    assert isinstance(request, Request), request
    line = next(row for row in request.message.splitlines() if "capex.heat_pump" in row)
    assert f"row {HEAT_PUMP['row']} | secondary | 2026 | {HEAT_PUMP['source']}" in line
    assert "1246.83 EUR/m [drilling-nl-2013-2300m, verified]" in request.message
    nameless = {**heat_pump, "row": {"source": "x"}}
    result = await call(ask_economics, {"values": [nameless, VALUES[4]]})
    message = result.output["error"]["message"]
    assert result.is_error and "the row's id" in message


def test_the_schema_says_a_row_is_its_id():
    """The tool's schema names the row's shape plainly: its id as text, others' fields listed."""
    schema = json.dumps(ask_economics.schema()["input_schema"])
    assert "the catalogue row's id" in schema
    assert '"year"' in json.dumps(ask_economics.schema()["input_schema"]["$defs"]["OtherRow"])


async def test_another_row_shows_its_status_and_another_basis_is_left_to_the_user():
    """The 3.87 EUR/kg row in ``others`` is labelled secondary; another basis is not converted.

    An ESP row per W electric is not converted to the key's shaft power: the user decides.
    """
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    waste = {
        "key": "opex.variable.waste_disposal",
        "value": 45.93,
        "unit": "EUR/kg",
        "row": "waste-disposal-norm-proxy-covra-2026",
        "status": "secondary",
        "others": [
            {
                "row": "waste-disposal-tfa-france-per-kg-filter-density",
                "value": 3.87,
                "unit": "EUR/kg",
                "status": "secondary",
            }
        ],
    }
    chp = {"key": "capex.chp", "value": 0.95, "unit": "EUR/W electric", "row": "chp-row"}
    tool_input = {"values": [*CATALOGUE_ROWS, ESP, waste, chp]}
    asked = ToolCall(id="q", name="ask_economics", input=tool_input)
    request = await dispatch(ask_economics, asked, Context(session=StubSession()))
    assert isinstance(request, Request), request
    lines = request.message.splitlines()
    line = next(line for line in lines if line.startswith("economics.opex.variable.waste"))
    assert "3.87 EUR/kg [waste-disposal-tfa-france-per-kg-filter-density, secondary]" in line
    pump = next(line for line in lines if line.startswith("economics.capex.production_pump"))
    assert "not converted" in pump and "the user decides" in pump
    plant = next(line for line in lines if line.startswith("economics.capex.chp"))
    assert "not converted" not in plant


class CatalogueWorkspace:
    """A workspace whose knowledge base holds the shipped cost catalogue."""

    def knowledge_search(self, query):
        """Find nothing; the tool reads the catalogue whole."""
        return []

    def knowledge_files(self):
        """Name the catalogue."""
        return [{"name": "data-economics.csv"}]

    def knowledge_file(self, name):
        """Return the catalogue's bytes, ``None`` for another document."""
        from pathlib import Path

        if name != "data-economics.csv":
            return None
        return (Path(__file__).parents[4] / "data/knowledge/data-economics.csv").read_bytes()


def catalogue_context():
    """Return a context whose run has the catalogue in its knowledge base."""
    from geomind.engine import Context
    from tests.fixtures.sessions import StubSession

    return Context(session=StubSession(workspace=CatalogueWorkspace()))


IDS = [
    {"key": "capex.heat_pump", "row": "heat-pump-dea-2025-10mw"},
    {
        "key": "capex.drilling",
        "row": "drilling-nl-2013-3000m",
        "others": ["drilling-nl-2013-2300m", "drilling-nl-2013-4000m"],
    },
    {"key": "discount_rate", "row": "discount-rate-pbl-sde-2025-geothermal-real"},
]
"""A question by row ids only, as the case lead sends it since run 86ddac2a."""


async def test_rows_named_by_id_are_read_from_the_knowledge_base():
    """Run 86ddac2a: copying every row's fields ran past the output limit; ids are enough."""
    from geomind.tools import dispatch
    from geomind.types import ToolCall

    asked = ToolCall(id="q", name="ask_economics", input={"values": IDS})
    request = await dispatch(ask_economics, asked, catalogue_context())
    assert isinstance(request, Request), request
    lines = request.message.splitlines()
    heat_pump = next(line for line in lines if line.startswith("economics.capex.heat_pump"))
    assert heat_pump.startswith("economics.capex.heat_pump = 0.737864 EUR/W | row heat-pump-dea")
    drilling = next(line for line in lines if line.startswith("economics.capex.drilling"))
    assert "1844.74 EUR/m" in drilling and "1246.83 EUR/m [drilling-nl-2013-2300m" in drilling
    rate = next(line for line in lines if line.startswith("economics.discount_rate"))
    assert "0.051" in rate and "verified" in rate


async def test_the_catalogue_value_wins_over_a_typed_one_and_is_set_on_approve_all():
    """A value the model typed for a named row is the row's; approve all sets the row's value."""
    from tests.fixtures.sessions import StubSession

    from geomind.context import ProblemState
    from geomind.engine import Context
    from tests.fixtures.cases import example_case

    typed = [{**IDS[0], "value": 9.99, "unit": "EUR/kW"}, *IDS[1:]]
    session = StubSession(workspace=CatalogueWorkspace())
    data, files = example_case("hackathon_2026")
    data.pop("economics")
    for file, content in files.items():
        if file != "economics.json":
            await session.save_artifact(f"case/{file}", content)
    context = Context(session=session, problem=ProblemState(case=data))
    answer = await economics_answered(context, {"values": typed}, "approve all")
    assert answer["economics"] == "set"
    [assumptions, _] = session.changes
    recorded = {change["value"]["id"]: change["value"] for change in assumptions}
    heat_pump = recorded["economics.capex.heat_pump"]
    assert heat_pump["value"] == {"value": 0.737864, "unit": "EUR/W"}
    assert heat_pump["citation"]["status"] == "secondary"


async def test_an_unknown_row_or_a_row_of_another_key_is_refused():
    """A row id must be in the catalogue and for the key it is named under."""
    unknown = [{"key": "capex.heat_pump", "row": "no-such-row"}, *IDS[1:]]
    from tests.fixtures.sessions import StubSession

    result = await call(
        ask_economics, {"values": unknown}, session=StubSession(workspace=CatalogueWorkspace())
    )
    message = result.output["error"]["message"]
    assert result.is_error and "no-such-row" in message and "heat-pump-dea-2025-10mw" in message
    other = [{"key": "capex.boiler", "row": "heat-pump-dea-2025-10mw"}, *IDS[1:]]
    result = await call(
        ask_economics, {"values": other}, session=StubSession(workspace=CatalogueWorkspace())
    )
    assert result.is_error
    assert "is for economics.capex.heat_pump" in result.output["error"]["message"]


def test_a_per_energy_map_with_an_open_kind_is_open_as_a_whole():
    """QA-105: a map with the chillers open gave no cost metric; every kind goes open."""
    from geomind.tools.gemini.economics import EconomicsValue, whole_per_energy

    values = [
        EconomicsValue(key="opex.per_energy.boiler", value=1, unit="EUR/MWh", source="s"),
        EconomicsValue(key="capex.boiler", value=2, unit="EUR/W", source="s"),
    ]
    kept, open_keys, moved = whole_per_energy(values, ["opex.per_energy.compression_chiller"])
    assert [item.key for item in kept] == ["capex.boiler"]
    assert set(open_keys) == {"opex.per_energy.compression_chiller", "opex.per_energy.boiler"}
    assert moved == ["opex.per_energy.boiler"]
    assert whole_per_energy(values, [])[2] == []


def test_a_percent_given_as_a_whole_number_on_a_fraction_key_is_refused():
    """QA-120: "8 %" was sent as discount_rate 8 with no unit, which reads as 800 %."""
    from geomind.tools.gemini.economics import refuse_percents

    with pytest.raises(ToolError, match=r"not 8 %. For a percent give the fraction"):
        refuse_percents([EconomicsValue(key="discount_rate", value=8, source="user")])
    refuse_percents([EconomicsValue(key="discount_rate", value=0.08, source="user")])


def test_a_value_other_than_the_approved_one_is_named_and_refused():
    """QA-168: a lead approved 0.5 EUR/(W/K) for the heat exchanger and wrote 0.1089 EUR/W."""
    from geomind.context import ProblemState
    from geomind.context.state import Assumption
    from geomind.tools.gemini.economics import refuse_unapproved, unapproved_economics

    approved = Assumption(
        id="economics.capex.heat_exchanger",
        text="approved",
        value={"value": 0.5, "unit": "EUR/(W/K)"},
        confirmed=True,
    )
    problem = ProblemState(assumptions=[approved])
    same = {"capex": {"heat_exchanger": {"value": 0.5, "unit": "EUR/(W/K)"}}, "about": {}}
    other = {"capex": {"heat_exchanger": {"value": 0.1089, "unit": "EUR/W"}}}
    new_key = {"capex": {"cooler": {"value": 0.1, "unit": "EUR/W"}}}
    assert unapproved_economics(problem, same) == []
    assert unapproved_economics(problem, new_key) == []
    lines = unapproved_economics(problem, other)
    assert lines == [
        "economics.capex.heat_exchanger: 0.1089 EUR/W, but the user approved 0.5 EUR/(W/K)"
    ]
    with pytest.raises(ToolError, match="call ask_economics"):
        refuse_unapproved(problem, other)


async def test_the_site_country_replaces_only_keys_it_has_a_row_for_and_keeps_the_base():
    """QA-279: 'Norwegian prices where they differ' kept no base value and took Dutch rows."""
    from geomind.tools import dispatch
    from geomind.types import ToolCall

    base = "knowledge/hackathon-2026-assumptions.md, section 1.4"
    values = [
        {"key": "discount_rate", "value": 0.05, "source": base},
        {"key": "revenue.cold", "value": 60, "unit": "EUR/MWh", "source": base},
        {"key": "energy.electricity", "value": 105.75, "unit": "EUR/MWh", "source": base},
    ]
    asked = ToolCall(id="q", name="ask_economics", input={"values": values, "country": "NO"})
    request = await dispatch(ask_economics, asked, catalogue_context())
    assert isinstance(request, Request), request
    lines = request.message.splitlines()
    rate = next(line for line in lines if line.startswith("economics.discount_rate"))
    assert rate.startswith("economics.discount_rate = 0.05 ") and "no row" in rate
    cold = next(line for line in lines if line.startswith("economics.revenue.cold"))
    assert "row cold-price-no-2017" in cold
    assert "Replaced by a row of Norway: economics.revenue.cold: 60 EUR/MWh" in request.message
    for line in lines:
        if line.startswith("economics.") and " = " in line:
            assert "prices of the Netherlands" not in line.split("(recommended")[0], line
            assert "prices of France" not in line.split("(recommended")[0], line


async def test_a_case_with_economics_is_asked_only_the_keys_it_lacks():
    """QA-268: after a denied change, the question replaced every reference value with rows."""
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    session = StubSession(workspace=CatalogueWorkspace())
    context = await case_context("hackathon_2026", session=session)
    asked = ToolCall(id="q", name="ask_economics", input={"values": []})
    request = await dispatch(ask_economics, asked, context)
    assert isinstance(request, Request), request
    lines = request.message.splitlines()
    assert not any(line.startswith("economics.discount_rate =") for line in lines)
    assert not any(line.startswith("economics.capex.heat_exchanger =") for line in lines)
    assert not any(line.startswith("economics.energy.electricity =") for line in lines)
    assert "Kept as the case has them, not asked again" in request.message


async def test_a_value_given_as_a_case_leaf_is_shown_as_a_number_and_a_bare_source_is_refused():
    """QA-298: {value: {value, unit}} was shown as a dict and failed on approve all."""
    from geomind.tools import dispatch
    from geomind.types import ToolCall

    base = "knowledge/hackathon-2026-assumptions.md, section 1.4"
    values = [
        {"key": "analysis_period", "value": {"value": 25, "unit": "yr"}, "source": base},
        {"key": "energy.gas", "value": 34.9514563107, "unit": "EUR/MWh", "source": base},
        {"key": "discount_rate", "value": 0.05, "source": base},
    ]
    asked = ToolCall(id="q", name="ask_economics", input={"values": values})
    request = await dispatch(ask_economics, asked, catalogue_context())
    assert isinstance(request, Request), request
    assert "economics.analysis_period = 25 yr | no row" in request.message
    assert "economics.energy.gas = 34.9515 EUR/MWh" in request.message
    assert "{'value'" not in request.message
    bare = [*values[:2], {"key": "discount_rate", "source": base}]
    result = await call(ask_economics, {"values": bare}, session=catalogue_context().session)
    assert result.is_error and "have a source and no value" in result.output["error"]["message"]
    text = [*values[1:], {"key": "analysis_period", "value": "25 years", "source": base}]
    result = await call(ask_economics, {"values": text}, session=catalogue_context().session)
    assert result.is_error and "analysis_period = '25 years'" in result.output["error"]["message"]


async def test_a_named_row_of_a_key_the_case_holds_is_not_proposed_again():
    """QA-268: after an applied change, the forced question named rows over the case's values."""
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    session = StubSession(workspace=CatalogueWorkspace())
    context = await case_context("hackathon_2026", session=session)
    values = [
        {
            "key": "accounting.allocation.heat_cost_share",
            "row": "heat-cost-share-pes-fiaschi-2021-high",
        },
        {"key": "discount_rate", "value": 0.06, "source": "user: discount rate 6 %"},
    ]
    asked = ToolCall(id="q", name="ask_economics", input={"values": values})
    request = await dispatch(ask_economics, asked, context)
    assert isinstance(request, Request), request
    assert "heat_cost_share" not in request.message
    assert "economics.discount_rate = 0.06 | no row | user" in request.message


async def test_the_country_of_the_case_site_picks_the_rows_without_being_named():
    """QA-085: about.site 'Trondheim, Norway' and the question still recommended Dutch rows."""
    from geomind.context import ProblemState
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.cases import example_case
    from tests.fixtures.sessions import StubSession

    data, _ = example_case("hackathon_2026")
    data.pop("economics")
    data["about"] = {**(data.get("about") or {}), "site": "Trondheim, Norway"}
    context = Context(
        session=StubSession(workspace=CatalogueWorkspace()), problem=ProblemState(case=data)
    )
    asked = ToolCall(id="q", name="ask_economics", input={"values": []})
    request = await dispatch(ask_economics, asked, context)
    assert isinstance(request, Request), request
    shown = [line.split(" (recommended")[0] for line in request.message.splitlines()]
    assert not any("prices of the Netherlands" in line for line in shown)
    assert "The site is in Norway" in request.message
    assert "name the site's country" not in request.message


class AssumptionsWorkspace(CatalogueWorkspace):
    """The catalogue and an assumptions document with an uncertainty table."""

    DOCUMENT = (
        "## Uncertainty ranges (studies only)\n\n| Key | `uncertainty` |\n|---|---|\n"
        '| `economics.discount_rate` | '
        '`{"kind": "normal", "std": 0.01, "min": 0.02, "max": 0.08}` |\n'
        '| `economics.energy.gas` | `{"kind": "triangular", "min": 25, "max": 70}` (EUR/MWh) |\n'
    )

    def knowledge_files(self):
        """Name the catalogue and the document."""
        return [*super().knowledge_files(), {"name": "assumptions.md"}]

    def knowledge_file(self, name):
        """Return the document's text, else the catalogue's bytes."""
        return self.DOCUMENT.encode() if name == "assumptions.md" else super().knowledge_file(name)


async def test_the_source_documents_ranges_go_in_as_uncertainty():
    """QA-259: the document's uncertainty table never reached the case."""
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    source = "knowledge/assumptions.md, section 1.4"
    values = [
        {"key": "discount_rate", "value": 0.05, "source": source},
        {"key": "energy.gas", "value": 39.92, "unit": "EUR/MWh", "source": source},
        {"key": "energy.electricity", "value": 105.75, "unit": "EUR/MWh", "source": source},
    ]
    context = Context(session=StubSession(workspace=AssumptionsWorkspace()))
    asked = ToolCall(id="q", name="ask_economics", input={"values": values})
    request = await dispatch(ask_economics, asked, context)
    assert isinstance(request, Request), request
    gas = "economics.energy.gas = 39.92 EUR/MWh (uncertainty triangular 25 to 70)"
    assert gas in request.message
    assert "(uncertainty normal std 0.01 0.02 to 0.08)" in request.message
    electricity = next(
        line for line in request.message.splitlines() if line.startswith("economics.energy.elec")
    )
    assert "uncertainty" not in electricity


async def test_the_question_counts_where_its_values_come_from_and_drops_a_false_note():
    """QA-314: the note said every value was the document; 8 keys were Dutch catalogue rows."""
    from geomind.engine import Context
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.sessions import StubSession

    source = "knowledge/assumptions.md, section 1.4"
    values = [
        {"key": "discount_rate", "value": 0.05, "source": source},
        {"key": "energy.gas", "value": 39.92, "unit": "EUR/MWh", "source": source},
    ]
    note = "Every value is the assumptions document, so results compare with the sample case."
    context = Context(session=StubSession(workspace=AssumptionsWorkspace()))
    asked = ToolCall(id="q", name="ask_economics", input={"values": values, "note": note})
    request = await dispatch(ask_economics, asked, context)
    assert isinstance(request, Request), request
    lines = request.message.splitlines()
    assert lines[1].startswith("Where the values come from: ")
    assert "2 from knowledge/assumptions.md" in lines[1]
    assert "from catalogue rows, general" in lines[1]
    assert note not in request.message
    period = next(line for line in lines if line.startswith("economics.analysis_period"))
    assert "subsidy-period" not in period and "25 yr" in period


class CaseDocumentWorkspace(CatalogueWorkspace):
    """The catalogue and an assumptions document written for the case ``my_case``."""

    DOCUMENT = (
        "## Economics\n\n| Item | Value | Source |\n|---|---|---|\n"
        "| Heat revenue (`revenue.heat`) | 60 EUR/MWh | Team |\n"
    )

    def knowledge_files(self):
        """Name the catalogue and the case's document."""
        return [*super().knowledge_files(), {"name": "my-case-assumptions.md"}]

    def knowledge_file(self, name):
        """Return the document's text, else the catalogue's bytes."""
        if name == "my-case-assumptions.md":
            return self.DOCUMENT.encode()
        return super().knowledge_file(name)


def case_document_context(workspace):
    """Return a context whose case ``my_case`` has no economics and names no country."""
    from geomind.context import ProblemState
    from geomind.engine import Context
    from tests.fixtures.cases import example_case
    from tests.fixtures.sessions import StubSession

    data, _ = example_case("hackathon_2026")
    data.pop("economics")
    data["name"] = "my_case"
    return Context(session=StubSession(workspace=workspace), problem=ProblemState(case=data))


async def test_a_value_the_case_s_own_document_gives_comes_from_it():
    """QA-320: the heat tariff came from a Dutch row while the case's document gave 60."""
    from geomind.tools import dispatch
    from geomind.types import ToolCall

    context = case_document_context(CaseDocumentWorkspace())
    tariff = {"key": "revenue.heat", "row": "heat-price-se-2019"}
    asked = ToolCall(id="q", name="ask_economics", input={"values": [tariff]})
    refused = await dispatch(ask_economics, asked, context)
    message = refused.output["error"]["message"]
    assert refused.is_error and "knowledge/my-case-assumptions.md" in message
    own = {
        "key": "revenue.heat",
        "value": 60,
        "unit": "EUR/MWh",
        "source": "knowledge/my-case-assumptions.md (Economics)",
    }
    asked = ToolCall(id="q", name="ask_economics", input={"values": [own]})
    assert isinstance(await dispatch(ask_economics, asked, context), Request)


async def test_a_case_with_no_country_gets_no_national_tariff_or_scheme():
    """QA-320: a Dutch heat tariff and SDE++ subsidy went into a case that names no country."""
    from geomind.tools import dispatch
    from geomind.types import ToolCall

    context = case_document_context(CatalogueWorkspace())
    asked = ToolCall(id="q", name="ask_economics", input={"values": []})
    request = await dispatch(ask_economics, asked, context)
    assert isinstance(request, Request), request
    lines = request.message.splitlines()
    assert not any(line.startswith("economics.revenue.heat =") for line in lines)
    assert not any(line.startswith("economics.revenue.subsidy") and "=" in line for line in lines)
    assert "economics.revenue.heat" in lines
    row = "sde-basisbedrag-geothermal-pbl-2026-over-20mw"
    subsidy = {"key": "revenue.subsidy.amount", "row": row}
    asked = ToolCall(id="q", name="ask_economics", input={"values": [subsidy]})
    refused = await dispatch(ask_economics, asked, context)
    assert refused.is_error and "names no country" in refused.output["error"]["message"]

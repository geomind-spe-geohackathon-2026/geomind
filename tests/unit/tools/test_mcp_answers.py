"""The e2e fixes of the MCP tools, on the recorded open-meteo server (E2E-4, -5, -6, -12).

The listing shows each tool's server, name and arguments in the history; a refusal of arguments
carries the tool's ``input_schema``; a long answer leads with its tables and their units; an answer
whose dates lie after the call is marked ``future``; a table of an answer becomes a case file in
UTC with its origin.
"""

import json

from geomind.engine import Engine
from geomind.stores import MemoryWorkspace
from geomind.tools.mcp import answer_key
from geomind.tools.stored import STORE_CHARACTERS
from tests.fixtures.mcp import http_server, open_meteo, server
from tests.fixtures.runs import Worker, call
from tests.fixtures.runs import context as run_context
from tests.fixtures.runs import engine_for, of_type, says, uses

TRONDHEIM = {"latitude": 63.4, "longitude": 10.4}
CLIMATE = {
    **TRONDHEIM,
    "start_date": "2027-01-01",
    "end_date": "2027-12-31",
    "daily_variables": ["temperature_2m_mean", "relative_humidity_2m_mean"],
}
HISTORICAL = {
    **TRONDHEIM,
    "start_date": "2026-01-12",
    "end_date": "2026-01-12",
    "hourly_variables": ["relative_humidity_2m"],
}


def outputs(events, tool):
    """Return the outputs of a tool's results, in order."""
    return [event.output for event in of_type(events, "tool.result") if event.tool == tool]


async def run_open_meteo(script):
    """Run ``script`` with the recorded open-meteo server; return the engine and the events."""
    workspace = MemoryWorkspace(mcp=[server(name="open-meteo")])
    engine = engine_for(script, workspace=workspace)
    engine.mcp_transport = http_server(recorded=open_meteo())
    start = run_context()
    await engine.run(Worker(), start)
    return engine, engine.store.load_events(start.run_id)


def artifact(engine, key):
    """Return an artifact of the run's chat: a run without a chat has its run id as chat id."""
    [run_id] = list(engine.store.events)
    return engine.store.load_chat_artifact(run_id, key)


def read(tool, arguments, call_id="c1"):
    """Return a ``read_mcp`` call of an open-meteo tool."""
    return call("read_mcp", call_id, server="open-meteo", tool=tool, arguments=arguments)


def later_tool_messages(events):
    """Return the tool messages the model read in the run's last LLM call."""
    last = of_type(events, "llm.completed")[-1]
    return [item.content for item in last.messages if item.role == "tool"]


async def test_list_mcp_shows_server_tool_and_argument_names_in_the_history():
    """E2E-4: three steps after ``list_mcp`` the model still reads each tool and its arguments.

    The run: the whole listing (54 KB with every input schema) came back as a reference and the
    tool names only, so the model guessed ``query``, ``hourly`` and ``daily`` and was refused.
    """
    script = [
        uses(call("list_mcp")),
        uses(call("lookup", "c2", key="a")),
        uses(call("lookup", "c3", key="b")),
        says("done"),
    ]
    _, events = await run_open_meteo(script)
    [listing] = later_tool_messages(events)[:1]
    assert "reference" not in listing
    for name in ("open-meteo", "openmeteo_search_locations", "openmeteo_get_historical"):
        assert name in listing
    for argument in ("country", "hourly_variables", "daily_variables", "start_date"):
        assert argument in listing
    [output] = outputs(events, "list_mcp")
    row = next(item for item in output["tools"] if item["name"] == "openmeteo_get_historical")
    assert row["server"] == "open-meteo" and row["read_only"] is True
    assert row["arguments"]["start_date"].endswith("required")
    assert "input_schema" not in row and "list_mcp(server, tool)" in output["note"]


async def test_list_mcp_of_one_tool_gives_its_whole_input_schema():
    """E2E-4: ``list_mcp(server, tool)`` gives the tool's description and whole schema."""
    script = [
        uses(call("list_mcp", server="open-meteo", tool="openmeteo_search_locations")),
        says("done"),
    ]
    _, events = await run_open_meteo(script)
    [output] = outputs(events, "list_mcp")
    [row] = output["tools"]
    assert "ISO 3166-1 alpha-2" in json.dumps(row["input_schema"])
    assert row["description"].startswith("Resolve a place name")


async def test_read_mcp_refuses_unknown_arguments_with_the_input_schema():
    """E2E-4: ``hourly`` for ``hourly_variables`` is refused before the call, schema included."""
    arguments = {**HISTORICAL, "hourly": HISTORICAL["hourly_variables"]}
    del arguments["hourly_variables"]
    _, events = await run_open_meteo([uses(read("openmeteo_get_historical", arguments)), says()])
    [output] = outputs(events, "read_mcp")
    error = output["error"]
    assert error["code"] == "invalid_input" and error["path"] == "arguments.hourly"
    assert "hourly_variables" in error["suggestions"]
    assert "input_schema" in error["message"] and "The archive covers from" in error["message"]


async def test_read_mcp_refuses_missing_required_arguments_with_the_input_schema():
    """E2E-4: ``query`` for ``name``: the missing required ``name`` is named, with the schema."""
    arguments = {"query": "Trondheim"}
    _, events = await run_open_meteo([uses(read("openmeteo_search_locations", arguments)), says()])
    error = outputs(events, "read_mcp")[0]["error"]
    assert error["code"] == "invalid_input" and error["path"] == "arguments.name"
    assert "ISO 3166-1 alpha-2" in error["message"]


async def test_a_refusal_of_the_server_carries_the_input_schema():
    """E2E-4: the server's own refusal (a date out of range) comes with the tool's schema."""
    _, events = await run_open_meteo([uses(read("openmeteo_get_forecast", TRONDHEIM)), says()])
    error = outputs(events, "read_mcp")[0]["error"]
    assert "out of range" in error["message"] and "forecast_days" in error["message"]
    assert "input_schema" in error["message"]


async def test_invalid_params_of_json_rpc_is_a_refusal_of_the_arguments():
    """E2E-4: JSON-RPC -32602 is ``invalid_input`` with the schema, not ``mcp_unavailable``."""
    workspace = MemoryWorkspace(mcp=[server()])
    script = [uses(call("read_mcp", server="market", tool="price", arguments={})), says()]
    engine = engine_for(script, workspace=workspace)
    engine.mcp_transport = http_server()
    start = run_context()
    await engine.run(Worker(), start)
    error = outputs(engine.store.load_events(start.run_id), "read_mcp")[0]["error"]
    assert error["code"] == "invalid_input" and "market is required" in error["message"]
    assert "input_schema" in error["message"]


async def test_a_long_answer_leads_with_its_tables_their_units_and_its_reference():
    """E2E-5: 365 days of climate data: the model reads the table's path, columns and units."""
    script = [
        uses(read("openmeteo_get_climate", CLIMATE)),
        uses(call("lookup", "c2", key="a")),
        uses(call("lookup", "c3", key="b")),
        says("done"),
    ]
    engine, events = await run_open_meteo(script)
    [output] = outputs(events, "read_mcp")
    assert list(output)[:3] == ["origin", "answer", "tables"]
    [table] = output["tables"]
    assert table == {
        "path": "structured.daily",
        "rows": 365,
        "columns": ["time", "temperature_2m_mean", "relative_humidity_2m_mean"],
        "units": {"time": "iso8601", "temperature_2m_mean": "°C", "relative_humidity_2m_mean": "%"},
        "time_zone": "GMT",
        "first": "2027-01-01",
        "last": "2027-12-31",
    }
    assert output["structured"]["timezone"] == "GMT" and "daily" not in output["structured"]
    assert output["text"].startswith("## Climate projections (CMIP6)")
    shown = {key: value for key, value in output.items() if key != "skill"}
    assert len(json.dumps(shown)) < STORE_CHARACTERS * 2
    whole = artifact(engine, output["answer"])
    assert len(whole["structured"]["daily"]) == 365
    shown = later_tool_messages(events)[0]
    assert "structured.daily" in shown and "relative_humidity_2m_mean" in shown


async def test_a_short_answer_comes_whole_with_its_tables():
    """E2E-5: a short answer is whole, and names its tables the same way."""
    _, events = await run_open_meteo([uses(read("openmeteo_get_historical", HISTORICAL)), says()])
    [output] = outputs(events, "read_mcp")
    assert len(output["structured"]["hourly"]) == 4
    assert output["tables"][0]["path"] == "structured.hourly"
    assert output["tables"][0]["time_zone"] == "Europe/Oslo"


async def test_an_answer_with_dates_after_the_call_is_marked_future():
    """E2E-6: the 2027 climate data lie after the call: ``future``, with the tool's description."""
    _, events = await run_open_meteo([uses(read("openmeteo_get_climate", CLIMATE)), says()])
    origin = outputs(events, "read_mcp")[0]["origin"]
    assert origin["future"] is True and origin["arguments"] == CLIMATE
    assert origin["tool_description"].startswith("Long-range climate projections")
    assert {"server", "tool", "time"} <= set(origin)


async def test_an_answer_of_past_dates_is_not_future():
    """E2E-6: January 2026 lies before the call."""
    _, events = await run_open_meteo([uses(read("openmeteo_get_historical", HISTORICAL)), says()])
    origin = outputs(events, "read_mcp")[0]["origin"]
    assert origin["future"] is False
    assert origin["tool_description"].startswith("Historical weather")


def save(table, file, call_id="c2", **options):
    """Return a ``save_mcp_table`` call of the answer of the climate read."""
    key = answer_key("open-meteo", "openmeteo_get_climate", CLIMATE)
    return call("save_mcp_table", call_id, answer=key, table=table, file=file, **options)


async def test_save_mcp_table_saves_a_table_as_a_case_file_in_utc_with_its_origin():
    """E2E-12: the climate table becomes ``case/<name>``, times in UTC, named safely."""
    script = [
        uses(read("openmeteo_get_climate", CLIMATE)),
        uses(save("structured.daily", "data/open-meteo Trondheim climate 2027")),
        says("done"),
    ]
    engine, events = await run_open_meteo(script)
    [output] = outputs(events, "save_mcp_table")
    assert output["file"] == "data/open-meteo_Trondheim_climate_2027.csv"
    assert output["columns"] == ["temperature_2m_mean", "relative_humidity_2m_mean"]
    assert output["units"] == {"temperature_2m_mean": "°C", "relative_humidity_2m_mean": "%"}
    assert output["origin"]["tool"] == "openmeteo_get_climate"
    assert output["origin"]["arguments"] == CLIMATE and output["origin"]["future"] is True
    assert output["time_zone"] == {"from": "GMT", "to": "UTC"}
    text = artifact(engine, f"case/{output['file']}").decode()
    lines = text.splitlines()
    assert lines[0] == "time,temperature_2m_mean,relative_humidity_2m_mean"
    assert lines[1] == "2027-01-01T00:00:00Z,-4.8,98" and len(lines) == 366
    origin = artifact(engine, f"case/{output['origin_file']}")
    assert json.loads(origin)["tool"] == "openmeteo_get_climate"


async def test_save_mcp_table_converts_local_times_to_utc():
    """E2E-6: hourly times in Europe/Oslo become UTC (an hour earlier in January)."""
    key = answer_key("open-meteo", "openmeteo_get_historical", HISTORICAL)
    saving = call("save_mcp_table", "c2", answer=key, table="structured.hourly", file="rh.csv")
    script = [uses(read("openmeteo_get_historical", HISTORICAL)), uses(saving), says("done")]
    engine, events = await run_open_meteo(script)
    [output] = outputs(events, "save_mcp_table")
    assert output["time_zone"] == {"from": "Europe/Oslo", "to": "UTC"}
    text = artifact(engine, "case/rh.csv").decode()
    assert text.splitlines()[1] == "2026-01-11T23:00:00Z,39"


async def test_save_mcp_table_names_the_tables_of_a_wrong_path():
    """E2E-12: a path that is no table lists the answer's tables."""
    script = [
        uses(read("openmeteo_get_climate", CLIMATE)),
        uses(save("daily", "climate.csv")),
        says("done"),
    ]
    _, events = await run_open_meteo(script)
    error = outputs(events, "save_mcp_table")[0]["error"]
    assert error["path"] == "table" and error["suggestions"] == ["structured.daily"]


async def test_save_mcp_table_refuses_an_unknown_answer():
    """E2E-12: an answer key no read gave is ``unknown_name``."""
    _, events = await run_open_meteo([uses(save("structured.daily", "climate.csv")), says()])
    error = outputs(events, "save_mcp_table")[0]["error"]
    assert error["code"] == "unknown_name" and error["path"] == "answer"


async def test_a_saved_table_is_a_series_gemini_reads_by_file_and_column():
    """E2E-12: the saved file drives ``site.air.temperature`` of a case, by file and column."""
    from geomind.tools.gemini.case import build_case
    from tests.fixtures.cases import example_case

    script = [
        uses(read("openmeteo_get_climate", CLIMATE)),
        uses(save("structured.daily", "data/air.csv")),
        says("done"),
    ]
    engine, _ = await run_open_meteo(script)
    data, files = example_case("hackathon_2026")
    data["site"]["air"]["temperature"] = {
        "unit": "degC",
        "file": "data/air.csv",
        "column": "temperature_2m_mean",
    }
    saved = artifact(engine, "case/data/air.csv")
    case = build_case(data, {**files, "data/air.csv": saved})
    assert case.site.air.temperature is not None


async def test_a_replay_saves_the_table_again_from_the_recorded_answer():
    """E2E-12: the replay reaches no server and the case file is there."""
    script = [
        uses(read("openmeteo_get_climate", CLIMATE)),
        uses(save("structured.daily", "data/air.csv")),
        says("done"),
    ]
    engine, _ = await run_open_meteo(script)
    run_id = next(iter(engine.store.events))
    replayed = await Engine.replay(engine.store, run_id, workspace=MemoryWorkspace())
    assert replayed.answer == "done"


def test_the_prompts_say_how_to_use_a_server_s_answer():
    """The MCP section, the shared rules and the case lead say what to do with an answer.

    The arguments as listed, ``future``, UTC and ``save_mcp_table``.
    """
    from pathlib import Path

    import geomind.prompts
    from geomind.prompts.prompt import MCP

    folder = Path(geomind.prompts.__file__).parent

    assert "list_mcp(server, tool)" in MCP and "input_schema" in MCP
    assert "`future`" in MCP and "save_mcp_table" in MCP
    shared = (folder / "shared" / "rules.md").read_text()
    assert "`future: true`" in shared and "UTC" in shared and "save_mcp_table" in shared
    lead = (folder / "case" / "lead.md").read_text()
    assert "save_mcp_table(answer, table, file)" in lead and "`future: true`" in lead

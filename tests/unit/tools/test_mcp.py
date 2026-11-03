"""The run's MCP servers as three tools: ``list_mcp``, ``read_mcp`` and ``call_mcp``."""

import json
from pathlib import Path
from types import SimpleNamespace

from geomind.engine import Engine, Permissions
from geomind.stores import MemoryWorkspace
from geomind.stores.run import FileRunStore
from geomind.tools.mcp import call_mcp, load_servers, server_of
from tests.fixtures.mcp import SECRET, http_server, server
from tests.fixtures.runs import Worker, call
from tests.fixtures.runs import context as run_context
from tests.fixtures.runs import engine_for, of_type, says, uses

OLD_LOG = Path(__file__).parents[2] / "fixtures" / "logs" / "mcp_0_4_22_dev41"


def results(events):
    """Return the output of each tool result, by tool."""
    return {event.tool: event.output for event in of_type(events, "tool.result") if event.call_id}


async def run_with_server(script, **options):
    """Run ``script`` with the fake server; return the engine, the result and the events."""
    engine = engine_for(script, workspace=MemoryWorkspace(mcp=[server()]), **options)
    engine.mcp_transport = http_server()
    start = run_context()
    result = await engine.run(Worker(), start)
    return engine, result, engine.store.load_events(start.run_id)


async def test_the_servers_are_listed_once_with_their_tools():
    """``price`` is read-only, ``order`` is not; a call names the server it reaches."""
    servers, failures = await load_servers([server()], 5, http_server())
    assert failures == [] and set(servers.rows["market"]) == {"price", "order"}
    assert servers.rows["market"]["price"]["read_only"] is True
    assert servers.rows["market"]["order"]["read_only"] is False
    assert server_of("read_mcp", {"server": "market"}) == "market"
    assert server_of("market__price") == "market" and server_of("read_case") is None


async def test_list_mcp_and_read_mcp_give_a_value_with_its_origin():
    """The agent lists the tools, reads a price, and the events name the server."""
    script = [
        uses(call("list_mcp")),
        uses(call("read_mcp", "c2", server="market", tool="price", arguments={"market": "TTF"})),
        says("TTF is 31.5 EUR/MWh"),
    ]
    _, result, events = await run_with_server(script)
    found = results(events)
    assert {item["name"] for item in found["list_mcp"]["tools"]} == {"price", "order"}
    assert found["read_mcp"]["structured"]["value"] == 31.5
    assert found["read_mcp"]["origin"]["server"] == "market"
    started = [event for event in of_type(events, "tool.started") if event.tool == "read_mcp"]
    assert result.answer == "TTF is 31.5 EUR/MWh" and started[0].mcp == "market"
    assert SECRET not in json.dumps([event.to_dict() for event in events])


async def test_read_mcp_refuses_a_tool_that_is_not_read_only():
    """``order`` changes something: ``read_mcp`` points to ``call_mcp``."""
    script = [
        uses(call("read_mcp", server="market", tool="order", arguments={})),
        says("done"),
    ]
    _, _, events = await run_with_server(script)
    error = results(events)["read_mcp"]["error"]
    assert error["code"] == "not_read_only" and "call_mcp" in error["message"]


async def test_call_mcp_asks_approval_only_for_a_tool_that_is_not_read_only():
    """In ``ask`` mode a read-only tool runs; another asks the user first."""
    reading = [
        uses(call("call_mcp", server="market", tool="price", arguments={"market": "TTF"})),
        says("done"),
    ]
    _, result, _ = await run_with_server(reading, permissions=Permissions(mode="ask"))
    assert result.status == "done"
    ordering = [uses(call("call_mcp", server="market", tool="order", arguments={})), says("done")]
    _, result, events = await run_with_server(ordering, permissions=Permissions(mode="ask"))
    requests = of_type(events, "request")
    assert result.status == "waiting" and requests[0].request.kind == "approval"


async def test_call_mcp_decides_by_the_effect_of_the_tool_it_calls():
    """The permissions see ``read`` for a read-only tool and ``external`` for another."""
    servers, _ = await load_servers([server()], 5, http_server())
    session = SimpleNamespace(engine=SimpleNamespace(mcp_servers=servers))
    assert call_mcp.for_call(session, {"server": "market", "tool": "price"}).effect == "read"
    assert call_mcp.for_call(session, {"server": "market", "tool": "order"}).effect == "external"
    assert call_mcp.effect == "external"


async def test_an_unknown_server_or_tool_names_what_there_is():
    """A wrong name answers ``unknown_name`` with a close match."""
    script = [uses(call("read_mcp", server="markt", tool="price", arguments={})), says("done")]
    _, _, events = await run_with_server(script)
    error = results(events)["read_mcp"]["error"]
    assert error["code"] == "unknown_name" and "market" in error["message"]


async def test_a_run_without_a_server_offers_no_mcp_tool_and_answers_mcp_unavailable():
    """No server: the three tools are not offered; a call anyway is ``mcp_unavailable``."""
    engine = engine_for([uses(call("list_mcp")), says("done")])
    start = run_context()
    await engine.run(Worker(), start)
    events = engine.store.load_events(start.run_id)
    output = results(events)["list_mcp"]
    assert "error" in output
    completed = of_type(events, "llm.completed")
    assert "## Connected servers" not in completed[0].messages[0].content


async def test_an_unreachable_server_is_left_out_with_an_error_and_no_header():
    """A failing server offers no tool; the run logs the failure, never the header's value."""
    workspace = MemoryWorkspace(mcp=[server()])
    engine = engine_for([uses(call("lookup", key="k")), says("done")], workspace=workspace)
    engine.mcp_transport = http_server(refuse=True)
    start = run_context()
    result = await engine.run(Worker(), start)
    events = engine.store.load_events(start.run_id)
    assert result.status == "done" and engine.mcp_servers.servers == {}
    assert of_type(events, "error")
    assert SECRET not in json.dumps([event.to_dict() for event in events])


async def test_a_replay_reuses_the_recorded_answer_and_never_reaches_the_server():
    """The replay of a run that called ``read_mcp`` has no transport and no server."""
    script = [
        uses(call("read_mcp", server="market", tool="price", arguments={"market": "TTF"})),
        says("TTF is 31.5 EUR/MWh"),
    ]
    engine, _, _ = await run_with_server(script)
    run_id = next(iter(engine.store.events))
    replayed = await Engine.replay(engine.store, run_id, workspace=MemoryWorkspace())
    assert replayed.answer == "TTF is 31.5 EUR/MWh"


async def test_an_old_log_with_a_server_s_tool_name_replays():
    """A log of 0.4.22.dev41 called ``market__price`` itself; its answer is reused."""
    store = FileRunStore(OLD_LOG)
    [run_id] = [path.name for path in OLD_LOG.iterdir()]
    replayed = await Engine.replay(store, run_id, workspace=MemoryWorkspace())
    assert replayed.answer == "TTF is 31.5 EUR/MWh"


async def test_an_agent_with_servers_reads_how_to_use_their_values():
    """The system prompt names the three tools and says a value is cited and confirmed."""
    _, _, events = await run_with_server([says("done")])
    system = of_type(events, "llm.completed")[0].messages[0].content
    assert "## Connected servers" in system and "confirms it" in system
    assert "`read_mcp(server, tool, arguments)`" in system

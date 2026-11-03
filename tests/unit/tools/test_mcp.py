"""The tools of a run's MCP servers: named ``<server>__<tool>``, read or external, with origin."""

import json

from geomind.engine import Context
from geomind.stores import MemoryWorkspace
from geomind.tools import dispatch
from geomind.tools.mcp import McpTool, load_tools, server_of
from geomind.types import ToolCall
from tests.fixtures.mcp import SECRET, http_server, server
from tests.fixtures.runs import Worker, call
from tests.fixtures.runs import context as run_context
from tests.fixtures.runs import engine_for, of_type, says, uses
from tests.fixtures.sessions import StubSession


async def test_the_server_s_tools_become_tools_of_the_run():
    """``market__price`` reads; ``market__order`` is external, so ``ask`` asks to approve it."""
    tools, failures = await load_tools([server()], 5, http_server())
    assert failures == [] and set(tools) == {"market__price", "market__order"}
    assert tools["market__price"].effect == "read" and tools["market__order"].effect == "external"
    assert server_of("market__price") == "market" and server_of("read_case") is None


async def test_a_call_returns_its_value_with_its_origin():
    """A value from a server carries the server, the tool and the time it came."""
    tools, _ = await load_tools([server()], 5, http_server())
    result = await dispatch(
        tools["market__price"],
        ToolCall(id="c1", name="market__price", input={"market": "TTF"}),
        Context(session=StubSession()),
    )
    assert result.output["structured"]["value"] == 31.5
    assert (
        result.output["origin"]["server"] == "market" and result.output["origin"]["tool"] == "price"
    )


async def test_an_unreachable_server_is_left_out_with_an_error_and_no_header():
    """A failing server offers no tool; the run logs the failure, never the header's value."""
    workspace = MemoryWorkspace(mcp=[server()])
    engine = engine_for([uses(call("lookup", key="k")), says("done")], workspace=workspace)
    engine.mcp_transport = http_server(refuse=True)
    start = run_context()
    result = await engine.run(Worker(), start)
    events = engine.store.load_events(start.run_id)
    assert result.status == "done" and engine.mcp_tools == {}
    errors = of_type(events, "error")
    assert (
        errors
        and "auth_refused" not in SECRET
        and SECRET not in json.dumps([event.to_dict() for event in events])
    )


async def test_a_run_offers_and_calls_a_server_s_tool_with_the_mcp_field():
    """The agent calls ``market__price``; the tool events name the server; no secret is logged."""
    workspace = MemoryWorkspace(mcp=[server()])
    script = [uses(call("market__price", market="TTF")), says("TTF is 31.5 EUR/MWh")]
    engine = engine_for(script, workspace=workspace)
    engine.mcp_transport = http_server()
    start = run_context()
    result = await engine.run(Worker(), start)
    events = engine.store.load_events(start.run_id)
    assert result.answer == "TTF is 31.5 EUR/MWh"
    started = [e for e in of_type(events, "tool.started") if e.tool == "market__price"]
    assert started and started[0].mcp == "market"
    assert SECRET not in json.dumps([event.to_dict() for event in events])


def test_a_tool_s_name_carries_its_server():
    """Two underscores join the server and the tool: OpenAI function names allow no dot."""
    tool = McpTool(
        server(),
        {"name": "price", "description": "", "read_only": True, "input_schema": {"type": "object"}},
        5,
    )
    assert tool.name == "market__price"


async def test_a_replay_reuses_the_recorded_answer_and_never_reaches_the_server():
    """The replay of a run that called ``market__price`` has no transport and no server."""
    from geomind.engine import Engine

    workspace = MemoryWorkspace(mcp=[server()])
    script = [uses(call("market__price", market="TTF")), says("TTF is 31.5 EUR/MWh")]
    engine = engine_for(script, workspace=workspace)
    engine.mcp_transport = http_server()
    start = run_context()
    await engine.run(Worker(), start)
    replayed = await Engine.replay(engine.store, start.run_id, workspace=workspace)
    assert replayed.answer == "TTF is 31.5 EUR/MWh"


async def test_an_agent_with_servers_reads_how_to_use_their_values():
    """The system prompt says a server's value is cited with its origin and confirmed."""
    workspace = MemoryWorkspace(mcp=[server()])
    engine = engine_for([says("done")], workspace=workspace)
    engine.mcp_transport = http_server()
    start = run_context()
    await engine.run(Worker(), start)
    started = [e for e in engine.store.load_events(start.run_id) if e.type == "llm.completed"]
    system = started[0].messages[0].content
    assert "## Connected servers" in system and "confirms it" in system

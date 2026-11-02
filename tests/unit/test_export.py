"""The export of a run: header, every LLM call, prompts, token tables and totals."""

import asyncio

from geomind.engine import Context, Engine, replay
from geomind.export import models_by_agent, render_export
from geomind.types import Message, Usage
from tests.fixtures.runs import Lead, Worker, call, context, engine_for, says, uses

CACHED = Usage(input_tokens=100, output_tokens=20, cost=0.5, cached_tokens=60)


def exported(manifest=None):
    """Run a lead that delegates once, and return its events and export."""
    completions = [
        uses(call("helper", task="find x"), usage=CACHED),
        uses(call("lookup", key="x")),
        says("x is 4"),
        says("The answer is 4.", usage=CACHED),
    ]
    engine = engine_for(completions)
    start = context("What is x?")
    asyncio.run(engine.run(Lead(), start))
    events = engine.store.load_events(start.run_id)
    return events, render_export(events, manifest)


def test_the_header_holds_the_request_loop_versions_and_models():
    """The export begins with the request, the loop, both versions and the model of each role."""
    manifest = {"geomind": {"version": "1.2.3"}, "gemini": {"version": "4.5.6"}}
    events = without_versions(exported()[0])
    text = render_export(events, manifest)
    header = text.split("## LLM calls")[0]
    assert "What is x?" in header and "gemini version: 4.5.6. geomind version: 1.2.3." in header
    assert "- lead: fake/model" in header and models_by_agent(events)["lead"] == ["fake/model"]


def without_versions(events):
    """Return the events as a 0.3.0 log has them: no ``versions`` on any run start."""
    return [
        event.model_copy(update={"versions": {}}) if event.type == "run.started" else event
        for event in events
    ]


def test_the_header_shows_the_versions_of_the_log():
    """A run records its versions, so the export needs no manifest."""
    events, text = exported()
    versions = events[0].versions
    assert set(versions) == {"geomind", "gemini", "python"}
    assert f"gemini version: {versions['gemini']}. geomind version: {versions['geomind']}." in text


def test_the_versions_of_the_log_win_over_the_manifest():
    """The manifest is only the fallback."""
    events, _ = exported()
    manifest = {"geomind": {"version": "1.2.3"}, "gemini": {"version": "4.5.6"}}
    text = render_export(events, manifest)
    assert "4.5.6" not in text and events[0].versions["gemini"] in text


def test_a_log_without_versions_falls_back_to_the_manifest():
    """A 0.3.0 log has no versions: the manifest is read, then not recorded."""
    events = without_versions(exported()[0])
    manifest = {"geomind": {"version": "1.2.3"}, "gemini": {"version": "4.5.6"}}
    assert "gemini version: 4.5.6. geomind version: 1.2.3." in render_export(events, manifest)
    assert "gemini version: not recorded" in render_export(events)


def test_the_header_shows_the_request_of_the_run_not_the_chat_history():
    """The run's messages hold the chat history first; the request is the last user message."""
    engine = engine_for([says("ok")])
    history = [
        Message(role="user", content="first question"),
        Message(role="assistant", content="first answer"),
        Message(role="user", content="second question"),
    ]
    start = Context(messages=history)
    asyncio.run(engine.run(Worker(), start))
    header = render_export(engine.store.load_events(start.run_id)).split("## LLM calls")[0]
    assert "second question" in header and "first question" not in header


def test_every_call_shows_messages_answer_tool_calls_and_tokens():
    """Calls come in order, with what each added, the tool calls and tokens in, cached, out."""
    text = exported()[1]
    assert text.count("### Call ") == 4
    assert text.index("### Call 1: lead") < text.index("### Call 2: lead.helper")
    assert "- helper(" in text and '"task": "find x"' in text
    assert "Tokens: 100 in (60 cached), 20 out, cost 0.5" in text


def test_prompts_come_once_in_the_appendix_and_tables_follow():
    """Each agent's system prompt is printed once; the tables and totals close the export."""
    text = exported()[1]
    appendix = text.split("## Appendix: system prompts")[1]
    assert appendix.count("### lead.helper_agent") == 1 and text.count("Work.") == 1
    assert "| lead | 2 | 200 | 120 | 40 | 1.0 |" in text
    assert "| 3 lead.helper_agent (step 2) | 1 | 10 | 0 | 5 | 0.01 |" in text
    assert text.rstrip().endswith("4 LLM calls, 220 in (120 cached), 50 out, cost 1.02.")


def test_the_export_of_a_replayed_run_equals_the_original(monkeypatch):
    """A replay logs the same calls, so its export is the same text."""
    stores = []

    class Kept(replay._ReplayStore):
        """A replay store that registers itself."""

        def __init__(self, *arguments):
            """Build the store and keep it."""
            super().__init__(*arguments)
            stores.append(self)

    engine = engine_for([uses(call("lookup", key="x")), says("done", usage=CACHED)])
    start = context("What is x?")
    asyncio.run(engine.run(Worker(), start))
    original = engine.store.load_events(start.run_id)
    monkeypatch.setattr(replay, "_ReplayStore", Kept)
    asyncio.run(Engine.replay(engine.store, start.run_id))
    replayed = [event for events in stores[0].events.values() for event in events]
    assert render_export(replayed) == render_export(original)

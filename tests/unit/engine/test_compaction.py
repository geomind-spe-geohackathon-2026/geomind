"""One compaction inside a run: the event, recovery and replay."""

from geomind import runtime
from geomind.engine import Engine
from geomind.engine.context import Context
from geomind.engine.recovery import recover
from geomind.runtime import FIXED_CHEAP_MODEL
from geomind.types import Message
from geomind.types.runlog import runlog
from tests.fixtures.runs import Worker, context, engine_for, of_type, run, says, types


def chat(turns, size=40):
    """Return a history of ``turns`` turns of ``size`` characters each."""
    messages = []
    for number in range(turns):
        messages.append(Message(role="user", content=f"{number}" + "q" * size))
        messages.append(Message(role="assistant", content="a" * size))
    return messages


async def compacted_run(script):
    """Run nine old turns plus one over a threshold of zero, keeping two turns."""
    with runtime.settings(compaction_threshold=0.0, compaction_keep_turns=2):
        engine = engine_for(script)
        start = Context(messages=[*chat(9), Message(role="user", content="now")])
        result = await engine.run(Worker(), start)
    return result, engine, engine.store.load_events(start.run_id)


async def test_nothing_happens_under_the_threshold():
    """A short chat costs no summary."""
    _, _, events = await run([says()])
    assert "compaction" not in types(events)


async def test_older_turns_become_one_summary_before_the_call():
    """The summary is logged, then the model sees it instead of the turns."""
    _, engine, events = await compacted_run([says("the summary"), says("answer")])
    compaction = of_type(events, "compaction")[0]
    assert (compaction.completion.text, compaction.turns) == ("the summary", 8)
    assert types(events).index("compaction") < types(events).index("llm.completed")
    sent = [message.content for message in engine.llm.llm.calls[1]["messages"]]
    assert any("the summary" in content for content in sent)
    assert not any(content.startswith("0q") for content in sent)


async def test_the_summarizer_runs_on_its_cheap_model_without_tools():
    """Its one call is what ``Summarizer`` declares."""
    _, engine, _ = await compacted_run([says("s"), says("a")])
    call = engine.llm.llm.calls[0]
    assert (call["model"], call["tools"]) == (FIXED_CHEAP_MODEL, [])
    assert "0qqq" in call["messages"][1].content


async def test_nothing_is_compacted_when_all_turns_are_kept():
    """A long open turn stays whole, and no summary is asked for."""
    with runtime.settings(compaction_threshold=0.0):
        _, _, events = await run([says()])
    assert "compaction" not in types(events)


async def test_the_summary_counts_as_usage():
    """The run pays for it, and the run log shows it."""
    result, _, events = await compacted_run([says("s"), says("a")])
    summary = of_type(events, "compaction")[0].completion.usage
    answer = of_type(events, "llm.completed")[0].completion.usage
    assert result.usage == summary + answer
    log = runlog(events)
    assert log["run"]["usage"]["input_tokens"] == result.usage.input_tokens
    assert len(log["steps"][0]["llm_calls"]) == 2


async def test_recovery_reuses_the_summary():
    """The rebuilt messages hold it, so nothing is summarized twice."""
    _, _, events = await compacted_run([says("s"), says("a")])
    state = recover(events)
    assert state.problem.compaction.summary == "s"
    assert state.problem.compaction.turns == 8
    assert sum(message.content.endswith("\ns") for message in state.messages) == 1


async def test_a_replay_gets_the_same_summary_back():
    """Recorded summaries are part of the script, so a replay spends nothing."""
    _, engine, _ = await compacted_run([says("s"), says("answer")])
    run_id = next(iter(engine.store.events))
    result = await Engine.replay(engine.store, run_id)
    assert result.answer == "answer"


async def test_a_context_outside_a_long_chat_is_left_alone():
    """Compaction changes the messages of the run, not those of the context."""
    start = context()
    with runtime.settings(compaction_threshold=0.0, compaction_keep_turns=0):
        await engine_for([says("s"), says("a")]).run(Worker(), start)
    assert [message.content for message in start.messages] == ["go"]

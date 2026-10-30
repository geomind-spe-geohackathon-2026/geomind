"""Pausing and resuming in one process, for each point and each answer."""

import pytest

from swarmax.core import runtime
from swarmax.core.engine import Permissions
from swarmax.core.engine.hooks import Cancellation, Hook, RequireApproval
from swarmax.core.types import Request
from swarmax.errors import RequestError, RunError
from tests.fixtures.runs import (
    EXECUTED,
    Worker,
    call,
    context,
    engine_for,
    of_type,
    says,
    uses,
)


@pytest.fixture(autouse=True)
def clean_run():
    """Forget executed tools."""
    EXECUTED.clear()
    with runtime.settings(retry_delay=0):
        yield


async def paused(script, **options):
    """Run until the first pause; return ``(engine, result)``."""
    options.setdefault("permissions", Permissions(mode="ask"))
    engine = engine_for(script, **options)
    result = await engine.run(Worker(), context())
    assert result.status == "waiting"
    return engine, result


async def resume(engine, result, answer):
    """Answer the pending request from the stored checkpoint."""
    checkpoint = engine.store.load_checkpoint(result.run_id)
    return await engine.resume(checkpoint, result.request.id, answer)


async def test_approval_runs_the_stored_call_once():
    """The exact call runs, and the run goes on."""
    engine, result = await paused([uses(call("save_note", text="x")), says("end")])
    assert EXECUTED == []
    final = await resume(engine, result, {"approved": True})
    assert final.answer == "end" and EXECUTED == ["save_note"]


async def test_denial_becomes_the_tool_result():
    """The model reads the reason and goes on."""
    engine, result = await paused([uses(call("save_note", text="x")), says("end")])
    final = await resume(engine, result, {"approved": False, "reason": "not now"})
    events = engine.store.load_events(final.run_id)
    assert final.answer == "end" and EXECUTED == []
    assert of_type(events, "tool.result")[0].output == "not now"


async def test_answer_to_a_question_becomes_its_result():
    """``ask_user`` pauses with options, and the reply is what the tool returns."""
    engine, result = await paused(
        [uses(call("ask_user", question="which?", options=["a", "b"])), says("end")]
    )
    assert result.request.kind == "question" and result.request.options == ("a", "b")
    assert of_type(engine.store.load_events(result.run_id), "request")[0].data()["options"]
    final = await resume(engine, result, {"text": "b"})
    assert final.answer == "end"
    recorded = of_type(engine.store.load_events(final.run_id), "tool.result")[0]
    assert (recorded.output, recorded.source) == ("b", "answer")


async def test_approval_applies_to_that_call_only():
    """The next call of the same tool asks again."""
    script = [
        uses(call("save_note", "a", text="1")),
        uses(call("save_note", "b", text="2")),
        says("end"),
    ]
    engine, first = await paused(script)
    second = await resume(engine, first, {"approved": True})
    assert second.status == "waiting" and second.request.call_id == "b"
    final = await resume(engine, second, {"approved": True})
    assert final.answer == "end" and EXECUTED == ["save_note", "save_note"]


async def test_the_same_hook_is_not_asked_again_for_that_call():
    """A hook that asked once does not ask again after the approval."""

    class Asks(Hook):
        count = 0

        def before_tool_call(self, agent, call):
            self.count += 1
            return Request(kind="approval", message="ok?")

    hook = Asks()
    engine, result = await paused([uses(call("lookup", key="k")), says("end")], hooks=[hook])
    final = await resume(engine, result, {"approved": True})
    assert final.answer == "end" and hook.count == 1


async def test_two_paused_calls_in_one_step():
    """The first runs after its approval, and the second then asks."""
    script = [uses(call("save_note", "a", text="1"), call("save_note", "b", text="2")), says("end")]
    engine, first = await paused(script)
    second = await resume(engine, first, {"approved": True})
    assert second.request.call_id == "b" and EXECUTED == ["save_note"]
    final = await resume(engine, second, {"approved": False})
    assert final.answer == "end" and EXECUTED == ["save_note"]


async def test_concurrent_step_pauses_on_the_tool_that_asks():
    """Read tools of one step wait until the one that asks is answered."""
    script = [uses(call("lookup", "a", key="1"), call("add", "b", left=1, right=2)), says("end")]
    engine, result = await paused(script, hooks=[RequireApproval(["add"])])
    assert result.request.call_id == "b" and EXECUTED == []
    final = await resume(engine, result, {"approved": True})
    assert final.answer == "end" and sorted(EXECUTED) == ["add", "lookup"]


async def test_pause_before_the_answer():
    """An approved answer ends the run; a denied one goes back to the model."""

    class Check(Hook):
        def before_finish(self, agent, action):
            return Request(kind="approval", message="send?")

    engine, result = await paused([says("first"), says("second")], hooks=[Check()])
    final = await resume(engine, result, {"approved": True})
    assert final.answer == "first"

    engine, result = await paused([says("first"), says("second")], hooks=[Check()])
    next_pause = await resume(engine, result, {"approved": False, "reason": "redo"})
    assert next_pause.status == "waiting"
    sent = engine.llm.llm.calls[1]["messages"]
    assert [m.content for m in sent if m.role == "user"][-1] == "redo"


async def test_pause_of_the_finish_tool():
    """An approved ``finish`` ends the run with its answer."""

    class Check(Hook):
        def before_finish(self, agent, action):
            return Request(kind="approval", message="send?")

    engine, result = await paused([uses(call("finish", answer="a"))], hooks=[Check()])
    final = await resume(engine, result, {"approved": True})
    assert (final.stop_reason, final.answer) == ("finish", "a")


async def test_pause_before_an_llm_call():
    """An approved call proceeds; a denied one stops the run."""

    class Check(Hook):
        def before_llm_call(self, agent, messages):
            return Request(kind="approval", message="spend?")

    engine, result = await paused([says("end")], hooks=[Check()])
    assert (await resume(engine, result, {"approved": True})).answer == "end"

    engine, result = await paused([says("end")], hooks=[Check()])
    final = await resume(engine, result, {"approved": False, "reason": "too much"})
    assert (final.stop_reason, final.status) == ("denied", "failed")


async def test_a_reply_to_a_question_before_the_answer_is_a_message():
    """A hook can ask the user something; the reply joins the conversation."""

    class Ask(Hook):
        def before_finish(self, agent, action):
            return Request(kind="question", message="anything else?")

    engine, result = await paused([says("first")], hooks=[Ask()])
    final = await resume(engine, result, {"text": "no"})
    assert final.answer == "first"


async def test_unknown_request_id_raises():
    """A wrong id changes nothing."""
    engine, result = await paused([uses(call("save_note", text="x")), says()])
    checkpoint = engine.store.load_checkpoint(result.run_id)
    with pytest.raises(RequestError, match="expected"):
        await engine.resume(checkpoint, "other", {"approved": True})


async def test_already_answered_request_raises():
    """Answering twice is refused, even from the old checkpoint."""
    script = [uses(call("save_note", text="x")), says("end"), says("again")]
    engine, result = await paused(script)
    checkpoint = engine.store.load_checkpoint(result.run_id)
    await engine.resume(checkpoint, result.request.id, {"approved": True})
    with pytest.raises(RunError, match="already ended"):
        await engine.resume(checkpoint, result.request.id, {"approved": True})


async def test_answered_while_still_running_raises():
    """A second answer to a request settled in a run that goes on is refused."""
    script = [uses(call("save_note", "a", text="x")), uses(call("save_note", "b", text="y"))]
    engine, first = await paused(script)
    old = engine.store.load_checkpoint(first.run_id)
    await engine.resume(old, first.request.id, {"approved": True})
    with pytest.raises(RequestError):
        await engine.resume(old, first.request.id, {"approved": True})


async def test_wrong_answer_shape_raises():
    """An answer of the wrong shape changes nothing."""
    engine, result = await paused([uses(call("save_note", text="x")), says()])
    with pytest.raises(RequestError, match="approved"):
        await resume(engine, result, {"text": "yes"})
    assert (await resume(engine, result, {"approved": True})).status == "done"


async def test_cancellation_still_holds_for_an_approved_call():
    """An approval skips the hooks that asked, never the check for a cancelled run."""
    is_cancelled = []
    script = [uses(call("save_note", text="x")), says("end")]
    engine, result = await paused(script, hooks=[Cancellation(lambda: bool(is_cancelled))])
    is_cancelled.append(True)
    final = await resume(engine, result, {"approved": True})
    assert final.stop_reason == "cancelled" and EXECUTED == []

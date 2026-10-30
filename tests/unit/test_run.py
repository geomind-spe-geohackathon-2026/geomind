"""The facade: exactly the contract's use."""

import pytest

import geomind as gd
from geomind import runtime
from geomind.agents import Analyst, Assistant, CodeAssistant
from geomind.errors import ProviderError, RequestError, RunError
from geomind.providers import FakeLLM
from geomind.stores import MemoryRunStore
from tests.fixtures.runs import call, of_type, says, uses


@pytest.fixture(autouse=True)
def no_retry_delay():
    """Retry without sleeping."""
    with runtime.settings(retry_delay=0):
        yield


def run_of(script, **options):
    """Return a run with a scripted provider."""
    return gd.Run(message="hello", llm=FakeLLM(script), **options)


def test_start_answers():
    """The simplest use."""
    result = run_of([says("hi")]).start()
    assert (result.status, result.answer) == ("done", "hi")


async def test_astart_for_async_callers():
    """The same run inside an event loop."""
    assert (await run_of([says("hi")]).astart()).answer == "hi"


async def test_sync_form_inside_an_event_loop_raises():
    """The error says what to use."""
    with pytest.raises(RunError, match="astart"):
        run_of([says("hi")]).start()


def test_history_comes_before_the_message():
    """A chat continues."""
    llm = FakeLLM([says()])
    history = [gd.Message(role="user", content="before")]
    gd.Run(message="now", history=history, llm=llm).start()
    contents = [message.content for message in llm.calls[0]["messages"]]
    assert contents.index("before") < contents.index("now")


def test_run_started_reports_the_tool_loop():
    """The contract's event, with the chat in the log."""
    store = gd.stores.MemoryRunStore()
    run = run_of([says()], store=store, chat="c1", project="p1")
    run.start()
    event = of_type(store.load_events(run.id), "run.started")[0]
    assert event.data() == {"run": run.id, "loop": "tool", "agent": "analyst", "parent": None}
    assert (event.chat, event.project) == ("c1", "p1")


def test_default_llm_is_openrouter(monkeypatch):
    """Without a provider the run uses OpenRouter, and so needs a key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
        gd.Run(message="x")


def test_a_sandbox_chooses_the_code_assistant(tmp_path):
    """Without a sandbox the model is not offered code tools."""
    assert type(run_of([]).loop.agent) is Analyst
    assert type(run_of([], sandbox=gd.sandbox.LocalSandbox(tmp_path)).loop.agent) is CodeAssistant


def question_script():
    """Return a run that asks one question."""
    return [uses(call("ask_user", question="which?")), says("end")]


def test_load_and_resume_in_a_fresh_run(tmp_path):
    """Nothing survives but the files."""
    run = run_of(question_script(), store=gd.stores.FileRunStore(tmp_path))
    paused = run.start()
    assert paused.status == "waiting"

    fresh = gd.Run.load(
        run.id, llm=FakeLLM(question_script()[1:]), store=gd.stores.FileRunStore(tmp_path)
    )
    assert fresh.resume(paused.request.id, {"text": "this"}).answer == "end"


def test_resume_on_the_same_object():
    """The caller need not reload."""
    run = run_of(question_script())
    paused = run.start()
    assert run.resume(paused.request.id, {"text": "x"}).answer == "end"


async def test_aresume_for_async_callers():
    """The same resume inside an event loop."""
    run = run_of(question_script())
    paused = await run.astart()
    assert (await run.aresume(paused.request.id, {"text": "x"})).answer == "end"


def test_load_of_an_unknown_run_raises(tmp_path):
    """Nothing is stored."""
    with pytest.raises(RunError, match="expected a log"):
        gd.Run.load("nope", llm=FakeLLM([]), store=gd.stores.FileRunStore(tmp_path))


def test_resume_of_a_dead_run_continues_from_its_events():
    """A run with a logged completion continues without a second LLM call."""

    class Dying(gd.stores.MemoryRunStore):
        kind = "tool.started"

        def save_event(self, run_id, event):
            if event.type == self.kind:
                self.kind = None
                raise SystemExit
            super().save_event(run_id, event)

    store = Dying()
    permissions = gd.Permissions(mode="auto")
    run = run_of([uses(call("ask_user", question="q"))], store=store, permissions=permissions)
    with pytest.raises(SystemExit):
        run.start()
    fresh = gd.Run.load(run.id, llm=FakeLLM([]), store=store, permissions=permissions)
    paused = fresh.resume()
    assert paused.status == "waiting"


def test_load_takes_the_contract_keywords(tmp_path):
    """Sandbox and permissions are passed again, as hooks and callbacks are."""
    permissions = gd.Permissions(mode="readonly")
    sandbox = gd.sandbox.LocalSandbox(tmp_path)
    run = run_of(question_script())
    run.start()
    fresh = gd.Run.load(
        run.id, llm=FakeLLM([]), store=run.store, sandbox=sandbox, permissions=permissions
    )
    assert fresh.engine.permissions is permissions and fresh.engine.sandbox is sandbox


def test_cancel_stops_at_the_next_hook_point():
    """Cancelling from a callback ends the run."""
    run = run_of([uses(call("ask_user", question="q"))])

    class Canceller(gd.callbacks.Callback):
        def on_llm_call(self, engine, event):
            run.cancel()

    run.engine.callbacks.append(Canceller())
    result = run.start()
    assert (result.status, result.stop_reason) == ("cancelled", "cancelled")


def test_answering_twice_raises():
    """A second answer finds nothing to answer."""
    script = [uses(call("ask_user", question="a")), uses(call("ask_user", "c2", question="b"))]
    run = run_of(script)
    first = run.start()
    run.resume(first.request.id, {"text": "x"})
    with pytest.raises(RequestError):
        run.resume(first.request.id, {"text": "x"})


def test_an_agent_replaces_the_routing():
    """One agent can be tried by hand, and it is the one a loaded run rebuilds."""
    store = MemoryRunStore()
    run = run_of([says()], agent=Assistant(), store=store)
    result = run.start()
    assert type(gd.Run.load(result.run_id, llm=FakeLLM([]), store=store).loop.agent) is Assistant

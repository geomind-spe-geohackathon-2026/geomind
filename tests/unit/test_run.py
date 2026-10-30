"""The facade: exactly the contract's use."""

import pytest

import swarmax as sx
from swarmax.core import runtime
from swarmax.core.agents import Assistant, CodeAssistant
from swarmax.errors import ProviderError, RequestError, RunError
from swarmax.providers import FakeLLM
from tests.fixtures.runs import call, of_type, says, uses


@pytest.fixture(autouse=True)
def no_retry_delay():
    """Retry without sleeping."""
    with runtime.settings(retry_delay=0):
        yield


def run_of(script, **options):
    """Return a run with a scripted provider."""
    return sx.Run(message="hello", llm=FakeLLM(script), **options)


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
    history = [sx.Message(role="user", content="before")]
    sx.Run(message="now", history=history, llm=llm).start()
    contents = [message.content for message in llm.calls[0]["messages"]]
    assert contents.index("before") < contents.index("now")


def test_run_started_reports_the_tool_loop():
    """The contract's event, with the chat in the log."""
    store = sx.stores.MemoryRunStore()
    run = run_of([says()], store=store, chat="c1", project="p1")
    run.start()
    event = of_type(store.load_events(run.id), "run.started")[0]
    assert event.data() == {"run": run.id, "loop": "tool", "agent": "assistant", "parent": None}
    assert (event.chat, event.project) == ("c1", "p1")


def test_default_llm_is_openrouter(monkeypatch):
    """Without a provider the run uses OpenRouter, and so needs a key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
        sx.Run(message="x")


def test_a_sandbox_chooses_the_code_assistant(tmp_path):
    """Without a sandbox the model is not offered code tools."""
    assert type(run_of([]).loop.agent) is Assistant
    assert type(run_of([], sandbox=sx.sandbox.LocalSandbox(tmp_path)).loop.agent) is CodeAssistant


def question_script():
    """Return a run that asks one question."""
    return [uses(call("ask_user", question="which?")), says("end")]


def test_load_and_resume_in_a_fresh_run(tmp_path):
    """Nothing survives but the files."""
    run = run_of(question_script(), store=sx.stores.FileRunStore(tmp_path))
    paused = run.start()
    assert paused.status == "waiting"

    fresh = sx.Run.load(
        run.id, llm=FakeLLM(question_script()[1:]), store=sx.stores.FileRunStore(tmp_path)
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
    with pytest.raises(RunError, match="nothing is stored"):
        sx.Run.load("nope", llm=FakeLLM([]), store=sx.stores.FileRunStore(tmp_path))


def test_resume_of_a_dead_run_continues_from_its_events():
    """A run with a logged completion continues without a second LLM call."""

    class Dying(sx.stores.MemoryRunStore):
        kind = "tool.started"

        def save_event(self, run_id, event):
            if event.type == self.kind:
                self.kind = None
                raise SystemExit
            super().save_event(run_id, event)

    store = Dying()
    permissions = sx.Permissions(mode="auto")
    run = run_of([uses(call("ask_user", question="q"))], store=store, permissions=permissions)
    with pytest.raises(SystemExit):
        run.start()
    fresh = sx.Run.load(run.id, llm=FakeLLM([]), store=store, permissions=permissions)
    paused = fresh.resume()
    assert paused.status == "waiting"


class ContractOnly:
    """A store with exactly the eight methods of the contract, as the backend's may be."""

    def __init__(self):
        """Wrap a full store."""
        self.inner = sx.stores.MemoryRunStore()

    def __getattr__(self, name):
        """Offer everything but what the contract leaves out."""
        if name == "load_events":
            raise AttributeError(name)
        return getattr(self.inner, name)


def test_a_contract_only_store_resumes_requests_from_its_checkpoint():
    """Pause and resume need no ``load_events``."""
    store = ContractOnly()
    run = run_of(question_script(), store=store)
    paused = run.start()
    fresh = sx.Run.load(run.id, llm=FakeLLM(question_script()[1:]), store=store)
    assert fresh.resume(paused.request.id, {"text": "x"}).answer == "end"


def test_a_contract_only_store_refuses_crash_recovery():
    """It says why, instead of repeating recorded calls."""
    store = ContractOnly()
    run = run_of(question_script(), store=store)
    run.start()
    fresh = sx.Run.load(run.id, llm=FakeLLM([]), store=store)
    with pytest.raises(RunError, match="load_events"):
        fresh.resume()


def test_cancel_stops_at_the_next_hook_point():
    """Cancelling from a callback ends the run."""
    run = run_of([uses(call("ask_user", question="q"))])

    class Canceller(sx.callbacks.Callback):
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

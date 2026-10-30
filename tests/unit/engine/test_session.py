"""The active run: sandbox lifecycle and artifacts."""

from swarmax.engine.session import Stop, is_cancel
from swarmax.sandbox import LocalSandbox
from swarmax.types import Cancel, Deny
from tests.fixtures.runs import call, of_type, run, says, types, uses


def test_is_cancel():
    """Only a cancellation ends a run as cancelled."""
    assert is_cancel(Cancel(reason="x")) and not is_cancel(Deny(reason="x"))


def test_stop_defaults():
    """A stop has one reason."""
    assert Stop("answer").request is None


async def test_no_sandbox_is_provisioned_without_a_code_tool(tmp_path):
    """Provisioning is lazy."""
    _, _, events = await run([says()], sandbox=LocalSandbox(tmp_path))
    assert "sandbox.provisioned" not in types(events)


async def test_sandbox_is_provisioned_once_and_closed_at_the_end(tmp_path):
    """Two code tools share one sandbox, closed before the run ends."""
    result, _, events = await run(
        [
            uses(call("run_python", code="print(1)")),
            uses(call("run_python", "c2", code="print(2)")),
            says(),
        ],
        sandbox=LocalSandbox(tmp_path),
    )
    assert result.status == "done"
    assert len(of_type(events, "sandbox.provisioned")) == 1
    assert of_type(events, "sandbox.provisioned")[0].provider == "LocalSandbox"
    assert types(events).index("sandbox.closed") < types(events).index("run.finished")
    assert list(tmp_path.iterdir()) == []


async def test_without_a_sandbox_the_model_reads_why():
    """The run goes on, with an error result."""
    result, _, events = await run([uses(call("run_python", code="1")), says("sorry")])
    assert result.answer == "sorry"
    assert "no sandbox" in str(of_type(events, "tool.result")[0].output)

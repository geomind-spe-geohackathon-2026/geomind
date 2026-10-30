"""The contract ``runlog`` object, nested runs included."""

import pytest

from geomind.errors import RunError
from geomind.types import Completion, Message, Request, Usage
from geomind.types.events import (
    LLMCompleted,
    PermissionDecided,
    RequestMade,
    RunFinished,
    RunStarted,
    ToolRecorded,
)
from geomind.types.runlog import runlog

USAGE = Usage(input_tokens=2, output_tokens=3, cost=0.5)


def started(run_id, parent=None, parent_step=None, agent="assistant"):
    """Return the first event of a run."""
    return RunStarted(
        run_id=run_id,
        time="t0",
        agent=agent,
        parent=parent,
        run=run_id,
        loop="tool",
        root="root",
        agent_class="a:B",
        max_steps=3,
        chat="c",
        parent_step=parent_step,
    )


def completed(run_id, index, agent="assistant"):
    """Return one recorded completion."""
    return LLMCompleted(
        run_id=run_id,
        agent=agent,
        index=index,
        completion=Completion(text="hi", usage=USAGE, model="m"),
        messages=(Message(role="user", content="q"),),
        duration=0.1,
    )


def recorded(run_id, index, is_error=False):
    """Return one recorded tool result."""
    return ToolRecorded(
        run_id=run_id,
        agent="assistant",
        index=index,
        call_id="c",
        tool="t",
        input={"x": 1},
        output="o",
        is_error=is_error,
        duration=0.2,
    )


def finished(run_id):
    """Return the last event of a run."""
    return RunFinished(run_id=run_id, time="t9", status="done", stop_reason="answer")


def test_runlog_has_the_contract_shape():
    """The run and its steps carry exactly the contract fields."""
    log = runlog([started("root"), completed("root", 1), recorded("root", 1), finished("root")])
    assert log["run"] == {
        "id": "root",
        "chat": "c",
        "status": "done",
        "loop": "tool",
        "started": "t0",
        "ended": "t9",
        "usage": {"input_tokens": 2, "output_tokens": 3, "cost": 0.5},
    }
    assert log["steps"] == [
        {
            "index": 1,
            "agent": "assistant",
            "parent": None,
            "llm_calls": [
                {
                    "model": "m",
                    "messages": [
                        {"role": "user", "content": "q", "tool_calls": [], "tool_call_id": None}
                    ],
                    "answer": "hi",
                    "input_tokens": 2,
                    "output_tokens": 3,
                    "cost": 0.5,
                    "duration": 0.1,
                }
            ],
            "tool_calls": [
                {"call_id": "c", "tool": "t", "input": {"x": 1}, "output": "o", "duration": 0.2}
            ],
        }
    ]


def test_tool_error_is_marked():
    """A failed tool call has the optional ``error`` key."""
    log = runlog([started("root"), recorded("root", 1, is_error=True)])
    assert log["steps"][0]["tool_calls"][0]["error"] is True


def test_nested_run_points_to_the_delegating_step():
    """A child step names the parent step, and its cost counts."""
    log = runlog(
        [
            started("root"),
            completed("root", 2),
            started("child", parent="root", parent_step=2, agent="assistant.helper"),
            completed("child", 1, agent="assistant.helper"),
        ]
    )
    child = log["steps"][1]
    assert (child["agent"], child["parent"], child["index"]) == ("assistant.helper", 2, 1)
    assert log["run"]["usage"]["input_tokens"] == 4


def test_status_is_waiting_until_the_request_is_answered():
    """An open request means waiting and an answer means running."""
    request = Request(id="q", kind="approval", message="m")
    made = RequestMade(run_id="root", request=request, point="tool")
    answer = PermissionDecided(
        run_id="root", index=1, decision="answer", rule="user", request=request
    )
    assert runlog([started("root"), made])["run"]["status"] == "waiting"
    assert runlog([started("root"), made, answer])["run"]["status"] == "running"


def test_a_log_without_a_start_is_refused():
    """No root run means the log is incomplete."""
    with pytest.raises(RunError, match="run.started"):
        runlog([])

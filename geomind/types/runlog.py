"""Build the contract's ``runlog`` object from the events of a run, nested runs included."""

from geomind.errors import RunError
from geomind.types.events import LLM_EVENTS
from geomind.types.messages import Usage


def _llm_call(event):
    """Return the contract ``llm_call`` of one completion."""
    completion = event.completion
    return {
        "model": completion.model,
        "messages": [message.model_dump(mode="json") for message in event.messages],
        "answer": completion.text,
        "input_tokens": completion.usage.input_tokens,
        "output_tokens": completion.usage.output_tokens,
        "cost": completion.usage.cost,
        "duration": event.duration,
    }


def _tool_call(event):
    """Return the contract ``tool_call`` of one result."""
    call = {
        "call_id": event.call_id,
        "tool": event.tool,
        "input": event.input,
        "output": event.output,
        "duration": event.duration,
    }
    return {**call, "error": True} if event.is_error else call


def _step(steps, parents, event):
    """Return the step of an event, creating it on first sight."""
    key = (event.run_id, event.index)
    if key not in steps:
        steps[key] = {
            "index": event.index,
            "agent": event.agent,
            "parent": parents.get(event.run_id),
            "llm_calls": [],
            "tool_calls": [],
        }
    return steps[key]


def _status(events, finished):
    """Return the contract status of the root run."""
    if finished is not None:
        return finished.status
    settled = [event for event in events if _is_request_event(event)]
    return "waiting" if settled and settled[-1].type == "request" else "running"


def _is_request_event(event):
    """Tell whether an event opens or settles a pending request."""
    if event.type == "permission":
        return event.request is not None and event.decision != "wait"
    return event.type == "request"


def _run(events, root):
    """Return the contract ``run`` object."""
    finished = next(
        (e for e in events if e.type == "run.finished" and e.run_id == root.run_id), None
    )
    usage = Usage()
    for event in events:
        if event.type in LLM_EVENTS:
            usage += event.completion.usage
    return {
        "id": root.run_id,
        "chat": root.chat,
        "status": _status(events, finished),
        "loop": root.loop,
        "started": root.time,
        "ended": finished.time if finished else None,
        "usage": usage.model_dump(mode="json"),
    }


def runlog(events):
    """Return ``{run, steps}`` for ``GET /assistant/runs/{id}/log``.

    NOTE: ``parent`` of a step is the step of the parent run that delegated it, while ``parent`` of
    an event is the parent run id; both are as the contract defines them.
    """
    events = list(events)
    roots = [event for event in events if event.type == "run.started" and event.parent is None]
    if not roots:
        raise RunError("runlog: events = no run.started of a root run; expected a complete log")
    parents = {e.run_id: e.parent_step for e in events if e.type == "run.started"}
    steps = {}
    for event in events:
        if event.type in LLM_EVENTS:
            _step(steps, parents, event)["llm_calls"].append(_llm_call(event))
        if event.type == "tool.result" and event.call_id is not None:
            _step(steps, parents, event)["tool_calls"].append(_tool_call(event))
    return {"run": _run(events, roots[0]), "steps": list(steps.values())}

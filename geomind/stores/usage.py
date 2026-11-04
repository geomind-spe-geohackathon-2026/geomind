"""What earlier runs of a project spent, for a budget over the project."""

from pathlib import Path
from typing import Protocol

from geomind.stores.run import FileRunStore
from geomind.types import RULE_MODEL, Usage
from geomind.types.events import LLM_EVENTS
from geomind.types.results import AgentUsage, SessionContext, SessionUsage, TotalUsage


class UsageLedger(Protocol):
    """The backend's record of spending; sync, because a hook reads it from a worker thread."""

    def spent(self, project_id):
        """Return the ``Usage`` of every finished run of a project, as the backend stores it."""


class MemoryUsageLedger:
    """Keep the spending of projects in this process; ``add`` records a finished run."""

    def __init__(self):
        """Start empty."""
        self.totals = {}

    def add(self, project_id, usage):
        """Add the usage of one finished run to a project."""
        self.totals[project_id] = self.totals.get(project_id, Usage()) + usage

    def spent(self, project_id):
        """Return the usage of a project; an unknown project spent nothing."""
        return self.totals.get(project_id, Usage())


def _session_of(started, events):
    """Return what the run ``started`` began spent on its own calls, from the events of its log."""
    own = [event for event in events if event.run_id == started.run_id]
    steps = [event for event in own if event.type == "step.started"]
    calls = [event.completion for event in own if event.type in LLM_EVENTS]
    used = [
        event.completion.usage.input_tokens
        for event in own
        if event.type == "llm.completed" and event.completion.model != RULE_MODEL
    ]
    window = next((e.context_window for e in reversed(steps) if e.context_window), None)
    context = None
    if used:
        context = SessionContext(peak_used=max(used), last_used=used[-1], window=window)
    started_tools = {(e.index, e.call_id) for e in own if e.type == "tool.started"}
    return SessionUsage(
        session=started.run_id,
        agent=started.agent,
        parent=started.parent,
        model=next((e.model for e in reversed(steps) if e.model), None),
        steps=len({event.index for event in steps}),
        tool_calls=len(started_tools),
        usage=sum((completion.usage for completion in calls), Usage()),
        context=context,
    )


def _agent_of(agent, sessions):
    """Return the sessions of one agent added up."""
    return AgentUsage(
        agent=agent,
        sessions=len(sessions),
        steps=sum(session.steps for session in sessions),
        tool_calls=sum(session.tool_calls for session in sessions),
        usage=sum((session.usage for session in sessions), Usage()),
    )


def usage_report(events):
    """Return ``(sessions, agents, total)`` of the run tree whose log ``events`` is.

    A session is one run of one agent (the root run, a nested run of a delegation, the routing
    run), in the order they began, with its own model calls only: each call counts once, in the
    session that made it, so ``total`` is the sum of the sessions and of every completion of the
    log. ``agents`` groups the sessions by agent path, in the order the agents first ran.
    """
    events = list(events)
    started = [event for event in events if event.type == "run.started"]
    sessions = [_session_of(event, events) for event in started]
    by_agent = {}
    for session in sessions:
        by_agent.setdefault(session.agent, []).append(session)
    agents = [_agent_of(agent, items) for agent, items in by_agent.items()]
    usage = sum((session.usage for session in sessions), Usage())
    total = TotalUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_tokens=usage.cached_tokens,
        cost=usage.cost,
        steps=sum(session.steps for session in sessions),
        tool_calls=sum(session.tool_calls for session in sessions),
    )
    return sessions, agents, total


def _finished_usage(events, project_id):
    """Return the tree usage of a finished root run of the project, else ``None``."""
    root = next((e for e in events if e.type == "run.started" and e.parent is None), None)
    if root is None or root.project != project_id:
        return None
    if not any(e.type == "run.finished" and e.run_id == root.run_id for e in events):
        return None
    usage = Usage()
    for event in events:
        if event.type in LLM_EVENTS:
            usage += event.completion.usage
    return usage


class FileUsageLedger:
    """Sum the usage of the finished root runs of a project under a ``FileRunStore`` root.

    A root run counts once it has ``run.finished``: its usage is every completion of its log,
    nested runs included. A run that is still running or paused, nested runs (which share the
    log of their root) and the runs of other projects do not count, so a run being resumed is not
    counted until it ends, and its own earlier steps are counted once, by the budget's session.
    """

    def __init__(self, root=".runs"):
        """Remember the root folder of the run store."""
        self.root = root

    def spent(self, project_id):
        """Return the usage of the finished runs of a project."""
        total = Usage()
        folder = Path(self.root)
        if not folder.is_dir():
            return total
        store = FileRunStore(folder)
        for log in sorted(folder.glob("*/events.jsonl")):
            if log.parent.name == "chats":
                continue
            total += _finished_usage(store.load_events(log.parent.name), project_id) or Usage()
        return total

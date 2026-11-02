"""What earlier runs of a project spent, for a budget over the project."""

from pathlib import Path
from typing import Protocol

from geomind.types import Usage
from geomind.types.events import LLM_EVENTS, event_from_dict
from geomind.utils.json import read_lines


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
        for log in sorted(folder.glob("*/events.jsonl")):
            events = [event_from_dict(line) for line in read_lines(log)]
            total += _finished_usage(events, project_id) or Usage()
        return total

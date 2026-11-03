"""A stand-in for the engine's session, for tests below the engine."""

import asyncio

from geomind.types import Usage


class StubState:
    """The part of the run state that agents and hooks read."""

    def __init__(self):
        """Start with no usage."""
        self.step_usage = Usage()
        self.usage = Usage()
        self.step = 1
        self.run_id = "r1"
        self.parent = None


class StubSession:
    """Records what tools and agents ask of the run."""

    def __init__(self, workspace=None):
        """Start with nothing recorded."""
        self.state = StubState()
        self.workspace = workspace
        self.artifacts = {}
        self.index_lock = asyncio.Lock()
        self.documents_read = {}
        self.searches = set()
        self.changes = []
        self.errors = []
        self.child_limit = None
        self.decision = None
        self.completion = None
        self.result = None
        self.events = []

    async def save_artifact(self, key, data):
        """Keep an artifact."""
        self.artifacts[key] = data

    def load_artifact(self, key):
        """Return a kept artifact, or ``None``."""
        return self.artifacts.get(key)

    async def emit(self, kind, **fields):
        """Keep an event as ``(class, fields)``."""
        self.events.append((kind, fields))

    def versions(self):
        """Return fixed versions."""
        return {"geomind": "test"}

    async def change_state(self, changes):
        """Keep a change of the problem state; return the version it gives."""
        self.changes.append(list(changes))
        return len(self.changes)

    async def report_error(self, error, where):
        """Keep an internal error."""
        self.errors.append((error, where))

    async def delegate(self, agent, task):
        """Return the scripted nested result."""
        self.delegated = (agent, task)
        return self.result

    async def before_llm_call(self, agent, messages):
        """Return the scripted hook decision."""
        return self.decision

    async def complete(self, agent, messages):
        """Return the scripted completion and count it in the step."""
        self.state.step_usage = self.completion.usage
        return self.completion

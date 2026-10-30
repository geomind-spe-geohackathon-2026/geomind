"""What the model sees: a fixed order, so prompt caching works."""

from uuid import uuid4

from geomind.types import Message


def new_run_id():
    """Return a fresh run id."""
    return uuid4().hex


class Context:
    """The run id and the messages of a run, rendered for one agent.

    ``messages_for`` renders a stable prefix (the system prompt; tool schemas travel beside the
    messages), then the history, then the dynamic part last. The dynamic part is rendered anew for
    each call and never stored in the history. Large tool outputs are summaries with references
    already, as dispatch returned them. S2 adds the problem state, compaction and skills here.
    """

    def __init__(self, run_id=None, messages=(), *, chat=None, project=None, steps_left=None):
        """Hold the messages of a run; a new run gets a fresh id."""
        self.run_id = run_id or new_run_id()
        self.messages = messages if isinstance(messages, list) else list(messages)
        self.chat = chat
        self.project = project
        self.steps_left = steps_left

    def _prefix(self, agent):
        """Return the system message, or nothing for an agent without a prompt."""
        parts = [agent.prompt.render() if agent.prompt else "", agent.output.instructions()]
        text = "\n\n".join(part for part in parts if part)
        return (Message(role="system", content=text),) if text else ()

    def _dynamic(self):
        """Return what changes every step."""
        if self.steps_left is None:
            return ()
        return (Message(role="system", content=f"Steps left: {self.steps_left}"),)

    def messages_for(self, agent):
        """Return the messages of one LLM call."""
        return (*self._prefix(agent), *self.messages, *self._dynamic())

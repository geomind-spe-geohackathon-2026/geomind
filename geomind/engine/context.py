"""What the model sees: a fixed order, so prompt caching works."""

from uuid import uuid4

from geomind.context import ProblemState, render
from geomind.context.skills import skill_listing
from geomind.errors import RunError
from geomind.types import Message


def new_run_id():
    """Return a fresh run id."""
    return uuid4().hex


class Context:
    """The run id and the messages of a run, rendered for one agent.

    ``messages_for`` renders a stable prefix (the system prompt; tool schemas travel beside the
    messages), then the history, then the dynamic part last. The dynamic part is rendered anew for
    each call and never stored in the history: the steps left, then the problem state, the very
    last part of every call. Large tool outputs are summaries with references already, as dispatch
    returned them.

    ``session`` is the run this context belongs to. Agents, tools and hooks receive the context, so
    they reach the provider, the store and the sandbox through it.
    """

    def __init__(
        self,
        run_id=None,
        messages=(),
        *,
        chat=None,
        project=None,
        steps_left=None,
        problem=None,
        session=None,
    ):
        """Hold the messages of a run; a new run gets a fresh id."""
        self.run_id = run_id or new_run_id()
        self.messages = messages if isinstance(messages, list) else list(messages)
        self.chat = chat
        self.project = project
        self.steps_left = steps_left
        self.problem = problem if problem is not None else ProblemState()
        self._session = session

    @property
    def session(self):
        """Return the run of this context; a context outside a run has none."""
        if self._session is None:
            raise RunError("context: session = None; expected a context inside Engine.run")
        return self._session

    @property
    def usage(self):
        """Return what the run has used so far."""
        return self.session.state.usage

    def _prefix(self, agent):
        """Return the system message, or nothing for an agent without a prompt."""
        parts = [agent.prompt.render() if agent.prompt else "", agent.output.instructions()]
        parts.append(skill_listing() if "read_skill" in agent.tools() else "")
        text = "\n\n".join(part for part in parts if part)
        return (Message(role="system", content=text),) if text else ()

    def _dynamic(self):
        """Return what changes every step."""
        parts = () if self.steps_left is None else (f"Steps left: {self.steps_left}",)
        state = render(self.problem)
        parts += (state,) if state else ()
        return tuple(Message(role="system", content=part) for part in parts)

    def messages_for(self, agent):
        """Return the messages of one LLM call."""
        return (*self._prefix(agent), *self.messages, *self._dynamic())

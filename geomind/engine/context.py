"""What the model sees: a fixed order, so prompt caching works."""

from uuid import uuid4

from geomind import runtime
from geomind.context import ProblemState, render
from geomind.context.skills import skill_listing
from geomind.errors import RunError
from geomind.prompts.prompt import KNOWLEDGE, MCP, MEMORY, STORED_RESULTS
from geomind.tools.base import with_old_names
from geomind.tools.stored import is_long, shortened
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

    ``call_id`` is the id of the tool call the context was made for, ``None`` outside a call.
    ``session`` is the run this context belongs to. Agents, tools and hooks receive the context, so
    they reach the provider, and the store through it.
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
        call_id=None,
        stored=None,
    ):
        """Hold the messages of a run; a new run gets a fresh id."""
        self.run_id = run_id or new_run_id()
        self.messages = messages if isinstance(messages, list) else list(messages)
        self.chat = chat
        self.project = project
        self.steps_left = steps_left
        self.problem = problem if problem is not None else ProblemState()
        self._session = session
        self.call_id = call_id
        self.stored = stored if stored is not None else {}

    def for_call(self, call_id):
        """Return this context as one tool call sees it: the same run, with the id of the call."""
        return Context(
            self.run_id,
            self.messages,
            chat=self.chat,
            project=self.project,
            steps_left=self.steps_left,
            problem=self.problem,
            session=self._session,
            call_id=call_id,
            stored=self.stored,
        )

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
        parts.append(STORED_RESULTS if "read_stored" in agent.tools() else "")
        remembers = getattr(self._session, "memory", True) is not None
        parts.append(MEMORY if remembers and "search_memory" in agent.tools() else "")
        knows = getattr(self._session, "knows", lambda: True)()
        connected = getattr(self._session, "mcp_of", lambda agent: {})(agent)
        parts.append(MCP if connected else "")
        parts.append(KNOWLEDGE if knows and "search_rag" in agent.tools() else "")
        text = "\n\n".join(part for part in parts if part)
        return (Message(role="system", content=text),) if text else ()

    def _dynamic(self):
        """Return what changes every step."""
        parts = () if self.steps_left is None else (f"Steps left: {self.steps_left}",)
        state = render(self.problem)
        parts += (state,) if state else ()
        return tuple(Message(role="system", content=part) for part in parts)

    def _history(self, agent=None):
        """Return the messages, with the results the model has already read in their short form.

        A result stored whole is shown whole in the step after its call. From the next step on its
        message is the reference and an outline (``self.stored``), so the history stops carrying
        what the model has used; ``read_stored`` or the tool itself gives it again. The result of
        a tool that keeps its results (``Tool.keeps_result``, a document page) stays whole for the
        last ``compaction_keep_turns`` turns, then shrinks the same way. A message changes once,
        when its result becomes old, and never again, so the prefix before it stays the same for
        the provider's cache.
        """
        turns = [n for n, item in enumerate(self.messages) if item.role == "assistant"]
        last = turns[-1] if turns else -1
        kept = kept_calls(self.messages, agent)
        window = runtime.get("compaction_keep_turns") if kept else 0
        history = []
        for n, item in enumerate(self.messages):
            recent = item.tool_call_id in kept and sum(turn > n for turn in turns) <= window
            history.append(self._aged(item) if n < last and not recent else item)
        return history

    def _aged(self, message):
        """Return an older message, its stored result or its long call inputs in short form."""
        if message.role == "tool" and message.tool_call_id in self.stored:
            return message.model_copy(update={"content": self.stored[message.tool_call_id]})
        if message.role == "assistant" and any(is_long(call.input) for call in message.tool_calls):
            return message.model_copy(
                update={"tool_calls": tuple(map(shortened, message.tool_calls))}
            )
        return message

    def messages_for(self, agent):
        """Return the messages of one LLM call."""
        return (*self._prefix(agent), *self._history(agent), *self._dynamic())


def kept_calls(messages, agent):
    """Return the ids of the calls whose tool keeps its results, of ``agent``'s tools."""
    if agent is None:
        return set()
    tools = with_old_names(agent.tools())
    return {
        call.id
        for item in messages
        if item.role == "assistant"
        for call in item.tool_calls
        if getattr(tools.get(call.name), "keeps_result", False)
    }

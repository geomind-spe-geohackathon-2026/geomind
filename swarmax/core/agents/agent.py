"""An agent is to one decision what a gemini ``Module`` is to one tick.

It turns a context into an action and never loops by itself. Declarations go in ``__init__``,
behaviour in ``forward``. ``Agent.__setattr__`` registers what ``__init__`` assigns: an implicit
mechanism, listed in ``conventions.md``.
"""

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import pydantic

from swarmax.core import runtime
from swarmax.core.prompts import Prompt
from swarmax.core.types import Action, Record, Usage
from swarmax.errors import DeclarationError, OutputError
from swarmax.tools import Tool
from swarmax.utils.json import to_jsonable
from swarmax.utils.strings import did_you_mean, first_paragraph, join_names, join_path, snake_case


class Model(Record):
    """Which model an agent wants; ``name=None`` means the default model of ``sx.runtime``.

    ``fallbacks`` lists models tried in order when the provider keeps failing.
    """

    name: str | None = None
    temperature: float = 0
    max_tokens: int | None = None
    fallbacks: tuple[str, ...] = ()

    def __init__(self, name=None, **fields):
        """Take the name positionally, as a declaration reads best."""
        super().__init__(name=name, **fields)

    def resolved_name(self):
        """Return the name to call the provider with."""
        return self.name or runtime.get("default_model")

    def settings(self):
        """Return the settings a provider receives."""
        return {"temperature": self.temperature, "max_tokens": self.max_tokens}


@dataclass(frozen=True)
class Output:
    """The type of the final answer: ``str`` or a Pydantic model.

    A failed validation goes back to the model as feedback, up to ``max_retries``, then the run
    fails.
    """

    kind: type = str
    max_retries: int = 2

    def validate(self, answer):
        """Return the JSON-safe answer, or raise ``OutputError``."""
        if self.kind is str:
            if isinstance(answer, str):
                return answer
            raise OutputError(f"output: answer = {answer!r}; expected text")
        try:
            if isinstance(answer, str):
                return to_jsonable(self.kind.model_validate_json(answer))
            return to_jsonable(self.kind.model_validate(answer))
        except pydantic.ValidationError as error:
            raise OutputError(f"output: expected {self.kind.__name__}: {error}") from error

    def instructions(self):
        """Return what the system prompt adds for a typed answer, or an empty string."""
        if self.kind is str:
            return ""
        schema = json.dumps(self.kind.model_json_schema())
        return f"Give the final answer as JSON that fits this schema: {schema}"


class AgentResult(Record):
    """What one agent call produced; built by ``Agent.__call__``, never by agent code.

    ``decision`` is set when a ``before_llm_call`` hook stopped the call, and ``action`` is then
    ``None``.
    """

    action: Action | None = None
    messages: tuple[Any, ...] = ()
    usage: Usage = Usage()
    duration: float = 0.0
    decision: Any = None


_SLOTS = {"prompt": Prompt, "output": Output, "model": Model}


class _AgentMeta(type):
    """Seal an agent once its ``__init__`` has returned, so declarations stay in ``__init__``."""

    def __call__(cls, *args, **kwargs):
        """Build the agent, then refuse further declarations."""
        agent = super().__call__(*args, **kwargs)
        object.__setattr__(agent, "_is_sealed", True)
        return agent


class Agent(metaclass=_AgentMeta):
    """Base class: declare in ``__init__``, override ``forward`` only for a rule-based step.

    Constructor sections are ``# Agents``, ``# Prompt``, ``# Tools``, ``# Output``, ``# Model``.
    NOTE: unlike a gemini module, an agent has no ``__getattr__`` and refuses assignment after
    ``__init__``, because it has no persistent commands; the values of a run live in its session.
    """

    def __init__(self):
        """Start with no tools, no children, no prompt, a text output and the default model."""
        for name, value in (
            ("_tools", {}),
            ("_children", {}),
            ("_declared", set()),
            ("_parent", None),
            ("_attribute", None),
            ("_is_sealed", False),
            ("prompt", None),
            ("output", Output()),
            ("model", Model()),
        ):
            object.__setattr__(self, name, value)

    def __setattr__(self, name, value):
        """Register a declaration under its attribute name."""
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        self._check_declaration(name)
        if name in _SLOTS and isinstance(value, _SLOTS[name]):
            object.__setattr__(self, name, value)
        elif isinstance(value, Tool) and name not in _SLOTS:
            self._tools[name] = value if value.name == name else value.renamed(name)
            object.__setattr__(self, name, self._tools[name])
        elif isinstance(value, Agent) and name not in _SLOTS:
            self._add_child(name, value)
        else:
            self._refuse_unknown(name, value)
        self._declared.add(name)

    def _check_declaration(self, name):
        """Refuse a declaration in the wrong place or under a taken name."""
        where = f"{type(self).__name__}.{name}"
        if "_tools" not in self.__dict__:
            raise DeclarationError(f"{where}: assigned before super().__init__()")
        if self._is_sealed:
            raise DeclarationError(f"{where}: assigned after __init__; declare it in __init__")
        if name in self._declared or (hasattr(type(self), name) and name not in _SLOTS):
            raise DeclarationError(f"{where}: the name is already taken")

    def _add_child(self, name, child):
        """Adopt a child agent, whose path now starts with this one."""
        child._parent = self
        child._attribute = name
        self._children[name] = child
        object.__setattr__(self, name, child)

    def _refuse_unknown(self, name, value):
        """Raise for a value that is no declaration under this name."""
        suggestion = did_you_mean(name, [*_SLOTS, *self._tools, *self._children])
        raise DeclarationError(
            f"{type(self).__name__}.{name}: value = {value!r}; expected a Tool, an Agent, or "
            f"a Prompt, Output or Model under its own name{suggestion}"
        )

    @property
    def name(self):
        """Return the snake_case class name."""
        return snake_case(type(self).__name__)

    @property
    def path(self):
        """Return the dotted path from the root agent, as events and logs show it."""
        if self._parent is None:
            return self.name
        return join_path(self._parent.path, self._attribute)

    def tools(self, recurse=False):
        """Return the tools by name; with ``recurse``, children's tools by dotted name."""
        found = dict(self._tools)
        if not recurse:
            return found
        for name, child in self._children.items():
            found.update(
                {join_path(name, key): item for key, item in child.tools(recurse=True).items()}
            )
        return found

    def children(self):
        """Return the direct child agents."""
        return list(self._children.values())

    def named_agents(self):
        """Return this agent and every descendant by dotted path."""
        found = {self.path: self}
        for child in self.children():
            found.update(child.named_agents())
        return found

    def tool_schemas(self):
        """Return what a provider needs to offer this agent's tools."""
        return [item.schema() for item in self._tools.values()]

    @classmethod
    def help(cls):
        """Return the first docstring paragraph and the declarations."""
        agent = cls()
        return "\n".join(
            (
                first_paragraph(cls.__doc__ or cls.__name__),
                f"Agents: {join_names(agent._children)}",
                f"Tools: {join_names(agent._tools)}",
                f"Output: {agent.output.kind.__name__}",
                f"Model: {agent.model.resolved_name()}",
            )
        )

    async def complete(self, messages):
        """Call the LLM of the active run with this agent's model and tools."""
        completion = await runtime.active_run().complete(self, messages)
        return Action(text=completion.text, tool_calls=completion.tool_calls)

    async def forward(self, context):
        """Render the context and ask the model; override only for a rule-based step."""
        return await self.complete(context.messages_for(self))

    async def __call__(self, context):
        """Run ``before_llm_call`` hooks, then ``forward``; return an ``AgentResult``.

        ``on_llm_call`` callbacks run as the completion is logged.
        """
        session = runtime.active_run()
        messages = context.messages_for(self)
        decision = await session.before_llm_call(self, messages)
        if decision is not None:
            return AgentResult(messages=messages, decision=decision)
        started = perf_counter()
        action = await self.forward(context)
        return AgentResult(
            action=action,
            messages=messages,
            usage=session.state.step_usage,
            duration=perf_counter() - started,
        )

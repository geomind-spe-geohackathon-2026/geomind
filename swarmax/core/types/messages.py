"""What goes to and comes from a model: messages, tool calls, completions and usage."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Record(BaseModel):
    """Base of every swarmax record: frozen, strict about names, JSON-safe."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ToolCall(Record):
    """One call a model asks for; ``id`` comes from the model and pairs the result with it."""

    id: str
    name: str
    input: dict[str, Any] = {}


class Usage(Record):
    """Tokens and cost; ``a + b`` adds them up."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0

    def __add__(self, other):
        """Return the sum of two usages."""
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost=self.cost + other.cost,
        )


class Message(Record):
    """One message of a conversation."""

    role: Literal["user", "assistant", "tool", "system"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


class Completion(Record):
    """What a provider returns for one LLM call; ``raw`` is the JSON-safe provider response."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = Usage()
    model: str = ""
    raw: Any = None


class Action(Record):
    """What an agent decided in one step: text and tool calls."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


class ToolResult(Record):
    """The outcome of one dispatched call.

    ``output`` is what the model sees: for a large result, ``{reference, summary}`` with the full
    data in the store under ``reference``. ``is_validation`` marks a call the model got wrong.
    """

    call_id: str
    tool: str
    output: Any = None
    is_error: bool = False
    is_validation: bool = False
    duration: float = 0.0
    reference: str | None = None

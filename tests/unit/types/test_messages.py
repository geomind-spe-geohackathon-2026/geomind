"""Messages, tool calls, completions and usage."""

import pydantic
import pytest

from swarmax.types import Completion, Message, ToolCall, Usage


def test_usage_adds_up():
    """``+`` sums every field."""
    total = Usage(input_tokens=1, output_tokens=2, cost=0.5) + Usage(input_tokens=3, cost=0.25)
    assert total == Usage(input_tokens=4, output_tokens=2, cost=0.75)


def test_records_are_frozen_and_strict():
    """A record refuses changes and unknown fields."""
    message = Message(role="user", content="hi")
    with pytest.raises(pydantic.ValidationError):
        message.content = "x"
    with pytest.raises(pydantic.ValidationError):
        Message(role="user", extra=1)


def test_role_is_one_of_four():
    """Only the contract roles exist."""
    with pytest.raises(pydantic.ValidationError):
        Message(role="robot")


def test_completion_is_json_safe():
    """A completion with tool calls round-trips through JSON."""
    completion = Completion(text="t", tool_calls=(ToolCall(id="1", name="n", input={"a": 1}),))
    assert Completion.model_validate_json(completion.model_dump_json()) == completion

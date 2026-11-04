"""A completion whose output reached the call's limit is cut, whatever the provider reports."""

from geomind.engine.session import marked_cut
from geomind.types import Completion, ToolCall, Usage

CALL = ToolCall(id="c", name="ask_economics", input={})


def test_output_at_the_limit_is_marked_cut():
    """Run 86ddac2a: 16,000 of 16,000 tokens and an empty call, but no ``length`` reported."""
    completion = Completion(
        tool_calls=(CALL,), usage=Usage(output_tokens=16000), raw={"finish_reason": "tool_calls"}
    )
    marked = marked_cut(completion, 16000)
    assert marked.raw["finish_reason"] == "length"
    assert marked.raw["reported_finish_reason"] == "tool_calls"


def test_output_under_the_limit_or_without_one_is_kept():
    """Only a completion at its limit changes; a raw that is no dict is read as empty."""
    completion = Completion(usage=Usage(output_tokens=900), raw=None)
    assert marked_cut(completion, 16000) is completion
    assert marked_cut(completion, None) is completion
    already = Completion(usage=Usage(output_tokens=16000), raw={"finish_reason": "length"})
    assert marked_cut(already, 16000) is already

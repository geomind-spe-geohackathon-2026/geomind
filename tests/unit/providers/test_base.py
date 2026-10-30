"""The LLM protocol."""

import inspect

from swarmax.providers import LLM, FakeLLM


def test_protocol_is_the_contract_signature():
    """The contract fixes these parameters, keyword-only after ``tools``."""
    parameters = inspect.signature(LLM.complete).parameters
    assert list(parameters) == [
        "self",
        "messages",
        "tools",
        "model",
        "settings",
        "on_text",
    ]
    assert parameters["model"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["on_text"].default is None


def test_fake_matches_the_protocol():
    """The fake has the same parameter names."""
    assert list(inspect.signature(FakeLLM.complete).parameters) == list(
        inspect.signature(LLM.complete).parameters
    )

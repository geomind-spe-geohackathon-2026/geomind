"""The shipped assistants."""

from swarmax.core.agents import Assistant, CodeAssistant


def test_assistant_has_the_built_ins():
    """It answers with what it has."""
    assistant = Assistant()
    assert list(assistant.tools()) == ["ask_user", "finish"]
    assert assistant.path == "assistant" and assistant.prompt is not None


def test_code_assistant_adds_the_code_tools():
    """A sandboxed run can write and run code."""
    assert list(CodeAssistant().tools()) == [
        "ask_user",
        "finish",
        "run_python",
        "read_file",
        "write_file",
    ]

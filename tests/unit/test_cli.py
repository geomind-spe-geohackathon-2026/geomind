"""The command line, with the real OpenRouter class over a fake transport."""

import json
from pathlib import Path

import httpx
import pytest

from swarmax import cli, runtime
from swarmax.providers import OpenRouter


def stream(*chunks):
    """Return one streamed response."""
    lines = [f"data: {json.dumps(chunk)}" for chunk in chunks]
    return httpx.Response(200, text="\n\n".join([*lines, "data: [DONE]", ""]))


def answer(text):
    """Return a streamed answer with usage."""
    usage = {"prompt_tokens": 7, "completion_tokens": 3, "cost": 0.002}
    return stream({"choices": [{"delta": {"content": text}}]}, {"choices": [], "usage": usage})


def tool_call(name, arguments):
    """Return a streamed tool call."""
    function = {"name": name, "arguments": json.dumps(arguments)}
    piece = {"index": 0, "id": "c1", "function": function}
    return stream({"choices": [{"delta": {"tool_calls": [piece]}}]})


@pytest.fixture
def service(monkeypatch, tmp_path):
    """Run in a temporary folder against a scripted service; return its responses."""
    monkeypatch.chdir(tmp_path)
    responses = []

    def provider():
        transport = httpx.MockTransport(lambda request: responses.pop(0))
        return OpenRouter(api_key="sk-test", transport=transport)

    monkeypatch.setattr(cli, "OpenRouter", provider)
    with runtime.settings(retry_delay=0):
        yield responses


def run_folder():
    """Return the one run folder of the working directory."""
    return str(next(Path(".runs").iterdir()))


def test_run_prints_streamed_text_and_totals(service, capsys):
    """Text streams to the terminal, and totals follow."""
    service.append(answer("Hello"))
    assert cli.main(["run", "Say hello"]) == 0
    output = capsys.readouterr().out
    assert "Hello" in output and "done (answer)" in output and "tokens 7 in" in output


def test_run_asks_in_the_terminal(service, monkeypatch, capsys):
    """A question pauses, the terminal answers and the run resumes."""
    service += [tool_call("ask_user", {"question": "Which?"}), answer("Thanks")]
    monkeypatch.setattr("builtins.input", lambda prompt: "this one")
    assert cli.main(["run", "Ask me"]) == 0
    assert "Thanks" in capsys.readouterr().out


def test_run_passes_the_model(service, monkeypatch):
    """The option reaches the provider."""
    seen = []

    def reply(request):
        seen.append(json.loads(request.content)["model"])
        return answer("ok")

    transport = httpx.MockTransport(reply)
    monkeypatch.setattr(cli, "OpenRouter", lambda: OpenRouter(api_key="k", transport=transport))
    cli.main(["run", "x", "--model", "a/b"])
    assert seen == ["a/b"]


def test_run_with_a_failing_service_reports_it(service, capsys):
    """A failed run has a failing exit code."""
    service.append(httpx.Response(401, text="bad key"))
    assert cli.main(["run", "x"]) == 1
    assert "failed (error)" in capsys.readouterr().out


def test_replay_reproduces_a_run_offline(service, capsys):
    """After a run, the service is not needed."""
    service.append(answer("Hello"))
    cli.main(["run", "x"])
    capsys.readouterr()
    assert cli.main(["replay", run_folder()]) == 0
    assert capsys.readouterr().out.startswith("pass: 1 steps")


def test_replay_of_a_missing_run_reports_it(service, capsys):
    """A wrong folder is an error message, not a traceback."""
    assert cli.main(["replay", ".runs/nothing"]) == 1
    assert "no recorded" in capsys.readouterr().err


def test_show_prints_prompts_answers_and_tokens(service, capsys):
    """The log holds what happened, step by step."""
    service.append(answer("Hello"))
    cli.main(["run", "Say hello"])
    capsys.readouterr()
    assert cli.main(["show", run_folder(), "--format", "md"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("# Run ") and "## Step 1 (assistant)" in output
    assert "user: Say hello" in output and "answer: Hello" in output
    assert "7 tokens in" in output and "## Totals" in output


def test_show_prints_tools_and_plain_text(service, monkeypatch, capsys):
    """Without a format it is plain text, and tools appear."""
    service += [tool_call("ask_user", {"question": "Which?"}), answer("Thanks")]
    monkeypatch.setattr("builtins.input", lambda prompt: "x")
    cli.main(["run", "Ask me"])
    capsys.readouterr()
    cli.main(["show", run_folder()])
    output = capsys.readouterr().out
    assert "- Tool ask_user" in output and "output: x" in output


def test_sandbox_choice():
    """The option picks a provider."""
    assert cli._sandbox(None) is None
    assert type(cli._sandbox("docker")).__name__ == "DockerSandbox"


def test_show_marks_a_nested_step():
    """A delegated step names the step that delegated it."""
    log = {
        "run": {
            "id": "r",
            "status": "done",
            "usage": {"input_tokens": 1, "output_tokens": 1, "cost": 0},
        },
        "steps": [
            {"index": 1, "agent": "lead.helper", "parent": 2, "llm_calls": [], "tool_calls": []}
        ],
    }
    assert "Step 1 (lead.helper, delegated by step 2)" in cli.render_log(log, False)

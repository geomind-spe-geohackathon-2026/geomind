"""The command line, with the real OpenRouter class over a fake transport."""

import json
from pathlib import Path

import httpx
import pytest

from geomind import cli, runtime
from geomind.providers import FakeLLM, OpenRouter
from geomind.stores.run import FileRunStore
from geomind.utils.json import append_line
from tests.fixtures.cases import example_folder, example_names
from tests.fixtures.runs import ROUTE, call, says, uses


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


def routed_answer():
    """Return the coordinator's streamed route to the analyst."""
    return answer(json.dumps({"kind": "loop", "loop": "tool", "agent": "analyst"}))


@pytest.fixture
def service(monkeypatch, tmp_path):
    """Run in a temporary folder against a scripted service; return its responses."""
    monkeypatch.chdir(tmp_path)
    responses = []

    def provider():
        transport = httpx.MockTransport(lambda request: responses.pop(0))
        return OpenRouter(api_key="sk-test", transport=transport)

    monkeypatch.setattr(cli, "OpenRouter", provider)
    monkeypatch.setattr(cli, "_fetch_prices", lambda fetcher=None: None)
    with runtime.settings(retry_delay=0):
        yield responses


def run_folder():
    """Return the one run folder of the working directory."""
    return str(next(Path(".runs").iterdir()))


def test_run_prints_streamed_text_and_totals(service, capsys):
    """Text streams to the terminal, and totals follow."""
    service += [routed_answer(), answer("Hello")]
    assert cli.main(["run", "Say hello"]) == 0
    output = capsys.readouterr().out
    assert "Hello" in output and "done (answer)" in output and "tokens 14 in" in output
    assert '"kind"' not in output


def test_run_asks_in_the_terminal(service, monkeypatch, capsys):
    """A question pauses, the terminal answers and the run resumes."""
    service += [routed_answer(), tool_call("ask_user", {"question": "Which?"}), answer("Thanks")]
    monkeypatch.setattr("builtins.input", lambda prompt: "this one")
    assert cli.main(["run", "Ask me"]) == 0
    assert "Thanks" in capsys.readouterr().out


def test_run_passes_the_model(service, monkeypatch):
    """The option reaches the provider."""
    seen = []

    def reply(request):
        seen.append(json.loads(request.content)["model"])
        return routed_answer() if len(seen) == 1 else answer("ok")

    transport = httpx.MockTransport(reply)
    monkeypatch.setattr(
        cli, "OpenRouter", lambda: OpenRouter(api_key="sk-model-test", transport=transport)
    )
    cli.main(["run", "x", "--model", "a/b"])
    assert seen == [runtime.get("coordinator_model"), "a/b"]


def test_run_with_a_failing_service_reports_it(service, capsys):
    """A failed run has a failing exit code."""
    service.append(httpx.Response(401, text="bad key"))
    assert cli.main(["run", "x"]) == 1
    assert "failed (error)" in capsys.readouterr().out


def test_replay_reproduces_a_run_offline(service, capsys):
    """After a run, the service is not needed."""
    service += [routed_answer(), answer("Hello")]
    cli.main(["run", "x"])
    capsys.readouterr()
    assert cli.main(["replay", run_folder()]) == 0
    assert capsys.readouterr().out.startswith("pass: 1 steps")


def test_replay_prints_one_line_when_the_versions_differ(service, capsys):
    """A run recorded with another gemini replays; the difference is one line, not an error."""
    service += [routed_answer(), answer("Hello")]
    cli.main(["run", "x"])
    capsys.readouterr()
    folder = Path(run_folder())
    log = folder / "events.jsonl"
    log.write_text(log.read_text().replace('"gemini": "', '"gemini": "0.0.1+'))
    assert cli.main(["replay", str(folder)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("pass: 1 steps")
    assert lines[1].startswith("versions differ: gemini recorded 0.0.1+")


def test_replay_of_a_missing_run_reports_it(service, capsys):
    """A wrong folder is an error message, not a traceback."""
    assert cli.main(["replay", ".runs/nothing"]) == 1
    assert "no recorded" in capsys.readouterr().err


def test_show_prints_prompts_answers_and_tokens(service, capsys):
    """The log holds what happened, step by step."""
    service += [routed_answer(), answer("Hello")]
    cli.main(["run", "Say hello"])
    capsys.readouterr()
    assert cli.main(["show", run_folder(), "--format", "md"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("# Agent log") and "### Call 2: analyst" in output
    assert "Say hello" in output and "Hello" in output
    assert "Tokens: 7 in (0 cached), 3 out, cost 0.002" in output and "## Totals" in output


def test_show_md_has_token_tables_prompts_once_and_full_answers(service, capsys):
    """The export the report includes: tokens per agent, per step and in total; each prompt once."""
    long = "word " * 900
    service += [routed_answer(), answer(long)]
    cli.main(["run", "Say hello"])
    capsys.readouterr()
    cli.main(["show", run_folder(), "--format", "md"])
    output = capsys.readouterr().out
    assert "## Tokens by agent" in output and "## Tokens by step" in output
    assert "| analyst | 1 | 7 | 0 | 3 | 0.002 |" in output
    assert "| coordinator | 1 | 7 | 0 | 3 | 0.002 |" in output
    assert "| Total | 2 | 14 | 0 | 6 | 0.004 |" in output
    assert "## Appendix: system prompts" in output and output.count("## Role") == 2
    assert long.strip() in output


def test_show_prints_tools_and_plain_text(service, monkeypatch, capsys):
    """Without a format it is plain text, and tools appear."""
    service += [routed_answer(), tool_call("ask_user", {"question": "Which?"}), answer("Thanks")]
    monkeypatch.setattr("builtins.input", lambda prompt: "x")
    cli.main(["run", "Ask me"])
    capsys.readouterr()
    cli.main(["show", run_folder()])
    output = capsys.readouterr().out
    assert "- Tool ask_user" in output and "output: x" in output


def test_run_with_a_loop_skips_the_routing(service, capsys):
    """``--loop`` chooses the loop; the coordinator is not asked."""
    service.append(answer("Hello"))
    assert cli.main(["run", "Say hello", "--loop", "tool"]) == 0
    assert "Hello" in capsys.readouterr().out


def test_run_records_and_runs_again_offline_from_the_recording(service, capsys):
    """``--record`` writes the completions; ``--recording`` runs from them without the service."""
    service += [routed_answer(), answer("Hello")]
    assert cli.main(["run", "Say hello", "--record", "run.jsonl"]) == 0
    capsys.readouterr()
    assert cli.main(["run", "Say hello", "--recording", "run.jsonl"]) == 0
    assert "Hello" in capsys.readouterr().out
    assert service == []


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


def test_run_writes_a_manifest_beside_its_log(service, gm, capsys):
    """Commits, versions, input hashes, the model of each agent and the seeds, for the report."""
    import subprocess

    import geomind

    service += [routed_answer(), answer("Hello")]
    cli.main(["run", "Say hello"])
    manifest = json.loads((Path(run_folder()) / "run_manifest.json").read_text())
    repository = Path(geomind.__file__).parents[1]
    head = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    assert manifest["geomind"]["commit"] == head
    assert manifest["geomind"]["version"] == geomind.__version__
    assert manifest["gemini"]["version"] == gm.__version__
    assert len(manifest["gemini"]["commit"]) == 40
    assert manifest["inputs"] == {}
    assert manifest["models"] == {
        "coordinator": [runtime.get("coordinator_model")],
        "analyst": [runtime.get("default_model")],
    }
    assert manifest["seeds"]["temperature"] == 0
    assert manifest["run"]["id"] == Path(run_folder()).name


@example_names
def test_the_manifest_hashes_the_project_s_case_files(service, name, capsys):
    """The case, the files it names and the plants are hashed, so a run names the data it read."""
    import hashlib
    import shutil

    folder = example_folder(name)
    project = Path("site") / name
    shutil.copytree(folder, project, ignore=shutil.ignore_patterns("*.pdf", "*.md", "study*"))
    service += [routed_answer(), answer("Hello")]
    cli.main(["run", "Say hello", "--project", str(project)])
    manifest = json.loads((Path(run_folder()) / "run_manifest.json").read_text())
    plants = sorted(f"plants/{path.name}" for path in (folder / "plants").glob("*.json"))
    files = ["case.json", "economics.json", "data/demand.csv", *plants]
    for file in files:
        expected = hashlib.sha256((project / file).read_bytes()).hexdigest()
        assert manifest["inputs"][f"project/{file}"]["sha256"] == expected
    assert set(manifest["inputs"]) == {f"project/{file}" for file in files}


def test_a_design_run_needs_a_project_with_a_case(service, capsys):
    """The design loop has no fallback case: without one the command stops before any call."""
    assert cli.main(["run", "Design a plant", "--loop", "design"]) == 1
    assert "case.json" in capsys.readouterr().err
    Path("site/p1").mkdir(parents=True)
    assert cli.main(["run", "Design a plant", "--loop", "design", "--project", "site/p1"]) == 1
    assert "case.json" in capsys.readouterr().err


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
    assert "Step 1 (lead.helper, delegated by step 2)" in cli.render_log(log)


def test_run_replay_and_show_with_a_fake_llm(monkeypatch, tmp_path, capsys):
    """The three commands work with the scripted provider."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "OpenRouter", lambda: FakeLLM([ROUTE, says("Hello")]))
    assert cli.main(["run", "Say hello"]) == 0
    assert cli.main(["replay", run_folder()]) == 0
    assert cli.main(["show", run_folder()]) == 0
    assert "answer: Hello" in capsys.readouterr().out


def recording(tmp_path, *completions):
    """Write a recording and return its path."""
    path = tmp_path / "recording.jsonl"
    for completion in completions:
        append_line(path, completion.model_dump(mode="json"))
    return str(path)


def typed(monkeypatch, *lines):
    """Answer ``input`` with lines in order, then end of file."""
    answers = iter(lines)

    def reply(prompt):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", reply)


GOAL = {"op": "replace", "path": "/goal", "value": "Find the flow"}


def test_chat_shows_text_tools_and_the_state_after_a_turn(tmp_path, monkeypatch, capsys):
    """One turn prints the tool with its input, the text and the problem state."""
    monkeypatch.chdir(tmp_path)
    script = [uses(call("update_state", changes=[GOAL])), says("Noted")]
    typed(monkeypatch, "What is the flow?", "/quit")
    assert cli.main(["chat", "--recording", recording(tmp_path, *script)]) == 0
    output = capsys.readouterr().out
    assert "[analyst] update_state" in output and "Noted" in output
    assert "Goal: Find the flow" in output


def test_chat_keeps_the_state_and_history_across_turns(tmp_path, monkeypatch, capsys):
    """The second message of a chat continues the first."""
    monkeypatch.chdir(tmp_path)
    script = [uses(call("update_state", changes=[GOAL])), says("one"), says("two")]
    typed(monkeypatch, "first", "second", "/state")
    assert cli.main(["chat", "--recording", recording(tmp_path, *script)]) == 0
    assert capsys.readouterr().out.count("Goal: Find the flow") == 3
    runs = [path for path in Path(".runs").iterdir() if path.name != "chats"]
    chats = list(Path(".runs/chats").iterdir())
    assert len(runs) == 2 and len(chats) == 1
    assert len(FileRunStore(".runs").load_history(chats[0].name)) == 4


def test_chat_commands(tmp_path, monkeypatch, capsys):
    """The commands work before and after a turn; ``/reset`` starts a new chat."""
    monkeypatch.chdir(tmp_path)
    script = [uses(call("update_state", changes=[GOAL])), says("one")]
    lines = ("/state", "/log", "hello", "/log", "/reset", "/state", "/help", "", "/quit")
    typed(monkeypatch, *lines)
    assert cli.main(["chat", "--recording", recording(tmp_path, *script)]) == 0
    output = capsys.readouterr().out
    assert output.count("(the problem state is empty)") == 2
    assert "(no turn yet)" in output and "Run " in output and "commands: /state" in output


def test_chat_asks_for_a_question_in_the_terminal(tmp_path, monkeypatch, capsys):
    """A request is answered at the prompt and the run goes on."""
    monkeypatch.chdir(tmp_path)
    script = [uses(call("ask_user", question="Which well?")), says("Well 2")]
    typed(monkeypatch, "go", "well 2", "/quit")
    assert cli.main(["chat", "--recording", recording(tmp_path, *script)]) == 0
    assert "Well 2" in capsys.readouterr().out


def test_chat_works_with_any_agent_and_a_project(tmp_path, monkeypatch, capsys):
    """A skeleton can be tried, and a project becomes its workspace."""
    monkeypatch.chdir(tmp_path)
    typed(monkeypatch, "hello")
    arguments = ["--agent", "explainer", "--project", "site/p1"]
    assert cli.main(["chat", *arguments, "--recording", recording(tmp_path, says("Hi"))]) == 0
    assert "Hi" in capsys.readouterr().out


def test_chat_goes_live_through_the_provider(service, monkeypatch, capsys):
    """``--live`` uses OpenRouter, and ``--model`` reaches it."""
    service.append(answer("Hello"))
    typed(monkeypatch, "hi")
    assert cli.main(["chat", "--live", "--model", "a/b"]) == 0
    assert "Hello" in capsys.readouterr().out


def test_chat_needs_a_provider(capsys):
    """Without one it says what to pass."""
    assert cli.main(["chat"]) == 1
    assert "--live or --recording" in capsys.readouterr().err


def test_chat_refuses_an_unknown_agent(capsys):
    """A wrong name is a message, not a traceback."""
    assert cli.main(["chat", "--agent", "analist", "--live"]) == 1
    assert "did you mean 'analyst'" in capsys.readouterr().err


def test_run_stops_at_the_spending_cap(service, capsys):
    """``--max-tokens`` and ``--max-cost`` deny the next model call over the cap."""
    service += [routed_answer(), answer("Hello")]
    assert cli.main(["run", "Say hello", "--max-tokens", "5"]) == 1
    output = capsys.readouterr().out
    assert "(denied)" in output and "Hello" not in output
    service += [routed_answer(), answer("Hello")]
    assert cli.main(["run", "Say hello", "--max-cost", "0.001"]) == 1


def test_replay_says_when_nested_runs_were_reused(service, capsys, monkeypatch):
    """A run with a project replayed without --project prints one line about it."""
    service += [routed_answer(), answer("Hello")]
    cli.main(["run", "x"])
    capsys.readouterr()
    monkeypatch.setattr(cli, "nested_runs_reused", lambda events, workspace: True)
    assert cli.main(["replay", run_folder()]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == "nested runs reused: the run has a project; pass --project to replay them"


def test_a_project_cap_needs_a_project(service, capsys):
    """The project flags mean nothing without --project."""
    assert cli.main(["run", "x", "--project-max-cost", "1"]) == 1
    assert "need --project" in capsys.readouterr().err


def test_a_project_cap_counts_the_earlier_runs_of_the_project(service, capsys):
    """The first run (20 tokens) is under the cap; the second is denied before its first call."""
    project = str(Path("site") / "p1")
    Path(project).mkdir(parents=True)
    service += [routed_answer(), answer("Hello")]
    assert cli.main(["run", "x", "--project", project, "--project-max-tokens", "100000"]) == 0
    assert "denied" not in capsys.readouterr().out
    assert cli.main(["run", "x", "--project", project, "--project-max-tokens", "20"]) == 1
    assert "(denied)" in capsys.readouterr().out


def test_a_live_cost_cap_bounds_calls_with_the_prices_of_the_list(monkeypatch):
    """A live run's cost cap carries the fetched prices; a recording fetches none."""
    prices = {"fake/model": (1e-6, 2e-6)}
    args = cli._parser().parse_args(["run", "x", "--max-cost", "1"])
    with runtime.settings(
        default_model="fake/model", coordinator_model="fake/model", summarizer_model="fake/model"
    ):
        budget = cli._budgets(args, fetcher=lambda: prices)[0]
    assert budget.prices == prices and budget.bounds_input
    offline = cli._parser().parse_args(["run", "x", "--max-cost", "1", "--recording", "r"])
    assert cli._budgets(offline, fetcher=lambda: prices)[0].prices is None


def test_prices_that_cannot_be_fetched_are_said(capsys):
    """A failed fetch is reported and leaves the cap unbounded by prices."""

    def failing():
        raise OSError("down")

    assert cli._fetch_prices(failing) is None
    assert "prices: not fetched" in capsys.readouterr().out

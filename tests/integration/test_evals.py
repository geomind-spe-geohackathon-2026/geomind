"""The eval runner over a task folder, with the real ``Analyst``.

NOTE: the sample task of the phase needs gemini's tools, so these tasks use the tools the analyst
has now, and they cover every kind of criterion, pass and fail.
"""

import pytest
import yaml

from evals import run as evals
from evals.tasks_format import load_task
from geomind.utils.json import append_line
from tests.fixtures.runs import call, says, uses

GOAL = {"op": "replace", "path": "/goal", "value": "Find the depth"}
TASK = {
    "message": "How deep is the well?",
    "answers": ["2100 m"],
    "criteria": [
        {"kind": "number", "value": 2100, "tolerance": 1, "unit": "m"},
        {"kind": "tool", "tool": "update_state"},
        {"kind": "tool", "tool": "search_documents", "called": False},
        {"kind": "question", "contains": "depth"},
        {"kind": "state", "path": "/goal"},
    ],
}
SCRIPT = [
    uses(call("update_state", changes=[GOAL])),
    uses(call("ask_user", "c2", question="What is the depth?")),
    says("The well is 2100 m deep."),
]


def write_task(root, task=TASK, script=SCRIPT, name="depth"):
    """Write one task and its recording."""
    folder = root / "tasks" / "analyst"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.yaml").write_text(yaml.safe_dump(task))
    for completion in script:
        append_line(root / "recordings" / "analyst" / f"{name}.jsonl", completion.model_dump())


def test_a_task_passes_offline_and_writes_the_summary(tmp_path, capsys):
    """Every kind of criterion holds, and the report has the totals."""
    write_task(tmp_path)
    assert evals.main(["--agent", "analyst"], tmp_path) == 0
    summary = (tmp_path / "reports" / "summary.md").read_text()
    assert "| depth | pass | 3 | 2 |" in summary
    assert "Total: 1 of 1 passed, 3 steps, 2 tool calls" in summary
    assert summary in capsys.readouterr().out


@pytest.mark.parametrize(
    ("criterion", "message"),
    [
        ({"kind": "number", "value": 9, "tolerance": 1}, "number: expected 9"),
        ({"kind": "number", "value": 2100, "tolerance": 1, "unit": "bar"}, "number: expected"),
        ({"kind": "tool", "tool": "read_result"}, "tool: read_result"),
        ({"kind": "tool", "tool": "update_state", "called": False}, "tool: update_state"),
        ({"kind": "question", "contains": "pressure"}, "question: none holds"),
        ({"kind": "state", "path": "/design/plant"}, "state: /design/plant is not set"),
        ({"kind": "state", "path": "/requirements/R1"}, "state: /requirements/R1"),
    ],
)
def test_a_criterion_that_fails_is_reported(tmp_path, criterion, message):
    """A failing task fails the run and says why."""
    write_task(tmp_path, {**TASK, "criteria": [criterion]})
    assert evals.main(["--agent", "analyst"], tmp_path) == 1
    assert message in (tmp_path / "reports" / "summary.md").read_text()


def test_a_task_with_history_and_a_state_item_by_id(tmp_path):
    """History reaches the run, and a state path can name an item."""
    item = {"id": "A1", "text": "Depth", "value": 2100}
    change = {"op": "add", "path": "/assumptions/-", "value": item}
    task = {
        "message": "And the assumption?",
        "history": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}],
        "criteria": [{"kind": "state", "path": "/assumptions/A1/text"}],
    }
    write_task(tmp_path, task, [uses(call("update_state", changes=[change])), says("Done")])
    assert evals.main(["--agent", "analyst"], tmp_path) == 0


def test_a_question_without_a_reply_ends_the_run(tmp_path):
    """The criteria judge what happened so far, and nothing hangs."""
    task = {**TASK, "answers": [], "criteria": [{"kind": "question", "contains": "depth"}]}
    write_task(tmp_path, task)
    assert evals.main(["--agent", "analyst"], tmp_path) == 0


def test_a_missing_recording_fails_the_task(tmp_path):
    """An empty script ends the run with an error, which fails the task."""
    write_task(tmp_path, script=[])
    assert evals.main(["--agent", "analyst"], tmp_path) == 1
    assert "run: error" in (tmp_path / "reports" / "summary.md").read_text()


def test_no_tasks_is_said_plainly(tmp_path, capsys):
    """A skeleton agent has an empty folder."""
    assert evals.main(["--agent", "designer"], tmp_path) == 2
    assert "no tasks" in capsys.readouterr().err


def test_an_unknown_agent_is_said_plainly(tmp_path, capsys):
    """A typo gets a close match."""
    assert evals.main(["--agent", "analist"], tmp_path) == 2
    assert "did you mean 'analyst'" in capsys.readouterr().err


def test_live_needs_a_key(tmp_path, monkeypatch, capsys):
    """Without one, it stops before it spends anything."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert evals.main(["--agent", "analyst", "--live"], tmp_path) == 2
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err


def test_live_writes_the_recording_anew(tmp_path, monkeypatch):
    """A live run records what the service answered, replacing the old file."""
    write_task(tmp_path, script=[says("old")])

    class Service:
        secrets = ()

        def __init__(self):
            self.script = iter(SCRIPT)

        async def complete(self, messages, tools, *, model, settings, on_text=None):
            return next(self.script)

    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(evals, "OpenRouter", Service)
    assert evals.main(["--agent", "analyst", "--live"], tmp_path) == 0
    assert evals.main(["--agent", "analyst"], tmp_path) == 0


def test_a_task_file_is_checked_when_it_loads(tmp_path):
    """A criterion of an unknown kind is an error at once."""
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"message": "x", "criteria": [{"kind": "feeling"}]}))
    with pytest.raises(ValueError):
        load_task(path)

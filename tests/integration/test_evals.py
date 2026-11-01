"""The eval runner over a task folder, with the real ``Analyst``.

NOTE: the sample task of the phase needs gemini's tools, so these tasks use the tools the analyst
has now, and they cover every kind of criterion, pass and fail.
"""

import shutil

import pytest
import yaml

from evals import run as evals
from evals.tasks_format import load_task
from geomind.utils.json import append_line
from tests.fixtures import ROOT
from tests.fixtures.cases import example_folder
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


@pytest.fixture(scope="module")
def gemini_loaded():
    """Import gemini once; it takes more than one test call's budget."""
    import gemini

    return gemini


def test_the_shipped_analyst_tasks_pass_offline(gemini_loaded):
    """The tasks of ``evals/tasks/analyst`` pass from their recordings, with the real tools."""
    outcomes = evals.run_agent("analyst")
    assert len(outcomes) == 5
    assert [outcome.problems for outcome in outcomes] == [[]] * 5


@pytest.mark.parametrize("agent", ["designer", "explainer", "coordinator"])
def test_the_shipped_tasks_of_the_single_agents_pass_offline(gemini_loaded, agent):
    """Each agent's tasks pass from their recordings, with the real tools."""
    outcomes = evals.run_agent(agent)
    assert outcomes
    assert [outcome.problems for outcome in outcomes] == [[]] * len(outcomes)


@pytest.mark.slow
def test_the_challenge2_cases_pass_offline_through_the_design_loop(gemini_loaded):
    """The hackathon case and its three variants are verified against their own cases.

    NOTE: slow, because each task runs the design loop, optimises and simulates a year, twice.
    """
    outcomes = evals.run_agent("challenge2")
    assert [outcome.name for outcome in outcomes] == [
        "colder_reservoir",
        "hackathon",
        "more_cooling",
        "user_profile",
    ]
    assert [outcome.problems for outcome in outcomes] == [[]] * 4
    assert all(outcome.verdict["passed"] for outcome in outcomes)


def run_ignored(tmp_path, task):
    """Run a challenge2 task on the recording of a design that ignored the variant."""
    folder = tmp_path / "tasks" / "challenge2"
    folder.mkdir(parents=True)
    shutil.copy(evals.ROOT / "tasks" / "challenge2" / f"{task}.yaml", folder)
    recordings = tmp_path / "recordings" / "challenge2"
    recordings.mkdir(parents=True)
    shutil.copy(
        ROOT / "tests" / "fixtures" / "recordings" / f"{task}_ignored.jsonl",
        recordings / f"{task}.jsonl",
    )
    [outcome] = evals.run_agent("challenge2", root=tmp_path)
    return outcome


@pytest.mark.slow
def test_a_design_that_ignores_the_cooling_peak_fails_its_checks(gemini_loaded, tmp_path):
    """The hackathon design on the 15 MW case, unsized, fails gemini's checks and is rejected.

    NOTE: slow, because the design is simulated over the year.
    """
    outcome = run_ignored(tmp_path, "more_cooling")
    assert outcome.verdict["passed"] is False
    assert any(problem.startswith("verified") for problem in outcome.problems)
    assert "stop: repeated_failure" in outcome.answer
    assert "cool_users.unmet_sensible" in outcome.answer
    assert outcome.state["design"]["rejected"] == ["design/start"]
    assert "reference" not in outcome.state["design"]


@pytest.mark.slow
def test_a_design_that_ignores_the_colder_gradient_fails_by_its_numbers(gemini_loaded, tmp_path):
    """At 25 K/km the design still passes gemini's checks, so the case and the LCTS catch it.

    NOTE: slow, because the design is optimised and simulated over the year.
    """
    outcome = run_ignored(tmp_path, "colder_reservoir")
    assert outcome.verdict["passed"] is True
    kinds = sorted(problem.split(":")[0] for problem in outcome.problems)
    assert kinds == ["number", "state"]
    assert "gradient/value = 30" in "".join(outcome.problems)


PROJECTS = ROOT / "evals" / "projects"
UNMET = ("heating_supply", "cooling_supply")


@pytest.mark.parametrize("project", ["hackathon", "hackathon_plant", "more_cooling"])
def test_the_eval_cases_load_and_hold_the_demand_met_constraints(gemini_loaded, project):
    """Each case is gemini's hackathon case plus a limit of 1 W unmet on each grid."""
    case = gemini_loaded.Case.from_json(PROJECTS / project / "case.json")
    unmet = [item for item in case.to_dict()["constraints"] if item["quantity"] == "unmet"]
    assert [item["on"] for item in unmet] == list(UNMET)
    assert all(item["max"] == {"value": 1, "unit": "W"} for item in unmet)


def test_the_cases_differ_from_gemini_s_example_only_by_their_variant(gemini_loaded):
    """The copy keeps gemini's demand, and the cooling variant is its cooling column x 1.5."""
    import pandas as pd

    source = example_folder("hackathon_2026") / "demand.csv"
    assert (PROJECTS / "hackathon" / "demand.csv").read_bytes() == source.read_bytes()
    base = pd.read_csv(source)
    peak = pd.read_csv(PROJECTS / "more_cooling" / "demand.csv")
    assert peak["heating_demand_MWth"].equals(base["heating_demand_MWth"])
    assert (peak["cooling_demand_MWcool"] - 1.5 * base["cooling_demand_MWcool"]).abs().max() < 1e-3
    assert round(peak["cooling_demand_MWcool"].max(), 6) == 15.0


@pytest.mark.slow
@pytest.mark.parametrize(
    ("project", "passes"), [("hackathon_plant", True), ("more_cooling", False)]
)
def test_the_hackathon_plant_passes_its_case_and_fails_the_cooling_peak(
    gemini_loaded, project, passes
):
    """The hand-found design is verified on the base case and fails the 15 MW cooling peak."""
    import geomind as gd

    plant = gemini_loaded.Plant.from_json(PROJECTS / "hackathon_plant" / "plant.json")
    case = gemini_loaded.Case.from_json(PROJECTS / project / "case.json")
    verdict = gd.verify.verify(plant, gemini_loaded.simulate(plant, case), case)
    assert verdict["passed"] is passes
    failed = {item["name"] for item in verdict["failures"]}
    assert (failed >= {"cool_users.supply_in.temperature"}) is (not passes)

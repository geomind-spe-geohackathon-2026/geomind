"""The eval runner over a task folder, with the real ``Analyst``.

NOTE: the sample task of the phase needs gemini's tools, so these tasks use the tools the analyst
has now, and they cover every kind of criterion, pass and fail.
"""

import json
import os
import re
import shutil

import pytest
import yaml

from evals import run as evals
from evals.tasks_format import load_task
from geomind.stores import FileWorkspace
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


def test_a_task_passes_offline_and_writes_its_report(tmp_path, capsys):
    """Every kind of criterion holds, and the report has the totals."""
    write_task(tmp_path)
    assert evals.main(["--agent", "analyst"], tmp_path) == 0
    summary = (tmp_path / "reports" / "analyst.md").read_text()
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
    assert message in (tmp_path / "reports" / "analyst.md").read_text()


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
    assert "run: error" in (tmp_path / "reports" / "analyst.md").read_text()


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


def test_the_verdict_reads_the_artifacts_of_the_task_s_chat():
    """A task's design and result live in its chat, where the verification reads them."""
    from geomind.stores import MemoryRunStore

    store = MemoryRunStore()
    store.save_chat_artifact(evals.CHAT, "result/r1", {"plant": {}})
    assert evals.StoredArtifacts(store, evals.CHAT).load_artifact("result/r1") == {"plant": {}}


def test_the_shipped_analyst_tasks_pass_offline(gemini_loaded):
    """The tasks of ``evals/tasks/analyst`` pass from their recordings, with the real tools."""
    outcomes = evals.run_agent("analyst")
    assert len(outcomes) == 5
    assert [outcome.problems for outcome in outcomes] == [[]] * 5


@pytest.mark.parametrize(
    "agent", [pytest.param("designer", marks=pytest.mark.slow), "explainer", "coordinator"]
)
def test_the_shipped_tasks_of_the_single_agents_pass_offline(gemini_loaded, agent):
    """Each agent's tasks pass from their recordings, with the real tools.

    NOTE: the designer's tasks are slow, because they size a plant and run a real search.
    """
    outcomes = evals.run_agent(agent)
    assert outcomes
    assert [outcome.problems for outcome in outcomes] == [[]] * len(outcomes)


NAMES = [
    "colder_reservoir",
    "economist",
    "hackathon",
    "more_cooling",
    "tight_budget",
    "user_profile",
    "verifier",
]


@pytest.mark.slow
def test_the_challenge2_cases_pass_offline_through_the_design_loop(gemini_loaded):
    """The hackathon case, its variants and the roles' tasks are verified against their own cases.

    NOTE: slow, because each task runs the design loop, optimises and simulates a year, twice.
    """
    outcomes = evals.run_agent("challenge2")
    assert [outcome.name for outcome in outcomes] == NAMES
    assert [outcome.problems for outcome in outcomes] == [[]] * len(NAMES)
    verified = [outcome for outcome in outcomes if outcome.name != "tight_budget"]
    assert all(outcome.verdict["passed"] for outcome in verified)


@pytest.mark.slow
def test_the_alternatives_task_passes_offline_through_the_new_compare_loop(gemini_loaded):
    """Three families, one infeasible by gemini's own check: the others are verified and ranked.

    NOTE: slow, because each family is sized, optimised and simulated for a whole year.
    """
    [outcome] = evals.run_agent("alternatives")
    assert outcome.problems == []
    verdicts = {item["family"]: item["verdict"] for item in outcome.state["design"]["alternatives"]}
    assert verdicts == {"heat_only": "infeasible", "chiller": "verified", "heat_pump": "verified"}
    assert "| heat_only | infeasible |" in outcome.answer


@pytest.mark.slow
def test_the_compare_task_passes_offline_through_the_compare_loop(gemini_loaded):
    """Two topologies, one study: ``design.study``, ``design.reference`` and the verdict hold.

    NOTE: slow, because the recording's study searches and simulates both topologies.
    """
    [outcome] = evals.run_agent("compare")
    assert outcome.name == "two_families" and outcome.problems == []
    study = outcome.state["design"]["study"]
    assert len(study["runs"]) == 2 and study["method"] == "minimize"
    best = next(run["design"] for run in study["runs"] if run["ranks"]["lcts"] == 1)
    assert outcome.state["design"]["reference"] == best
    assert outcome.verdict["passed"] and outcome.state["verification"]["passed"]
    assert "| design | feasible | rank | lcts |" in outcome.answer


def test_the_report_has_a_table_per_loop_and_main_writes_it(tmp_path, capsys):
    """Each task runs through the three loops; a loop that cannot finish it meets fewer criteria."""
    write_task(tmp_path)
    assert evals.main(["--report"], tmp_path) == 0
    text = (tmp_path / "reports" / "summary.md").read_text()
    assert text + "\n" == capsys.readouterr().out
    assert [line for line in text.splitlines() if line.startswith("## ")] == [
        "## ToolLoop",
        "## DesignLoop",
        "## CompareLoop",
    ]
    assert "| analyst/depth | 5 of 5 | 3 | 2 | 45 | 0.0300 |" in text


@pytest.mark.slow
def test_the_report_of_cells_side_by_side_is_the_same_report(tmp_path):
    """``workers`` runs the cells of the report in processes of their own; the table is equal.

    NOTE: slow, because each process imports geomind and gemini anew.
    """
    write_task(tmp_path)
    alone = evals.report(tmp_path)
    assert without_times(evals.report(tmp_path, workers=2)) == without_times(alone)


@pytest.mark.slow
def test_the_report_command_takes_workers(tmp_path, capsys):
    """``--workers`` is passed to the report; without it the cells run one after another.

    NOTE: slow, because each process imports geomind and gemini anew.
    """
    write_task(tmp_path)
    assert evals.main(["--report", "--workers", "2"], tmp_path) == 0
    assert "## CompareLoop" in capsys.readouterr().out


def without_times(text):
    """Return a report with the time cells blanked: they differ from run to run."""
    return re.sub(r"\| [\d.]+ \|$", "| time |", text, flags=re.MULTILINE)


def test_the_checked_in_report_has_every_task_under_each_loop():
    """``evals/reports/summary.md`` has a table per loop, with a row for every task file."""
    text = (evals.ROOT / "reports" / "summary.md").read_text()
    tasks = sorted(
        f"{path.parent.name}/{path.stem}" for path in (evals.ROOT / "tasks").glob("*/*.yaml")
    )
    tables = text.split("## ")[1:]
    assert [table.splitlines()[0] for table in tables] == ["ToolLoop", "DesignLoop", "CompareLoop"]
    for table in tables:
        rows = [line.split(" | ")[0].removeprefix("| ") for line in table.splitlines()[4:]]
        assert [row for row in rows if row] == [*tasks, "Total"]


def report_cells():
    """Return one parameter per cell of the report: a task through a loop."""
    return [
        pytest.param(loop, path.parent.name, path.stem, id=f"{loop}-{path.parent.name}-{path.stem}")
        for loop in evals.REPORT_LOOPS
        for path in sorted((evals.ROOT / "tasks").glob("*/*.yaml"))
    ]


def checked_in_rows(loop):
    """Return the task rows of one loop's table in the checked-in report, times blanked."""
    text = (evals.ROOT / "reports" / "summary.md").read_text()
    table = text.split(f"## {evals.REPORT_LOOPS[loop]}\n")[1].split("\n## ")[0]
    lines = [line for line in table.splitlines() if line.startswith("| ") and "/" in line]
    return {without_times(line) for line in lines}


@pytest.mark.slow
@pytest.mark.parametrize(("loop", "folder", "task"), report_cells())
def test_each_row_of_the_checked_in_report_is_the_generated_one(gemini_loaded, loop, folder, task):
    """Each row of ``evals/reports/summary.md`` is what its cell gives, but for its time.

    NOTE: slow, because the cell runs its task through a loop. One test per cell, so the slow
    shards of CI share the report; the totals are checked by
    ``test_the_totals_of_the_checked_in_report_add_up``.
    """
    outcomes = evals._cell(evals.ROOT, folder, loop, task)
    rows = [evals._loop_row(evals._renamed(outcome, folder)) for outcome in outcomes]
    assert {without_times(row) for row in rows} <= checked_in_rows(loop)


def test_the_totals_of_the_checked_in_report_add_up():
    """Each loop's total is the sum of its rows, so a regenerated row cannot hide in it."""
    text = (evals.ROOT / "reports" / "summary.md").read_text()
    for title in evals.REPORT_LOOPS.values():
        table = text.split(f"## {title}\n")[1].split("\n## ")[0]
        rows = [line.split(" | ") for line in table.splitlines() if line.startswith("| ")][1:]
        *tasks, total = rows
        met = [cell.split(" of ") for cell in (row[1] for row in tasks)]
        assert total[1] == f"{sum(int(a) for a, _ in met)} of {sum(int(b) for _, b in met)}"
        for column in (2, 3, 4):
            assert int(total[column]) == sum(int(row[column]) for row in tasks)


def report_workers():
    """Return the processes of the report: one per usable core, at most eight."""
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    return min(cores or 1, 8)


def run_recorded(tmp_path, task, recording):
    """Run one challenge2 task on a recording that is not its own."""
    folder = tmp_path / "tasks" / "challenge2"
    folder.mkdir(parents=True)
    shutil.copy(evals.ROOT / "tasks" / "challenge2" / f"{task}.yaml", folder)
    recordings = tmp_path / "recordings" / "challenge2"
    recordings.mkdir(parents=True)
    shutil.copy(recording, recordings / f"{task}.jsonl")
    [outcome] = evals.run_agent("challenge2", root=tmp_path)
    return outcome


def run_ignored(tmp_path, task):
    """Run a challenge2 task on the recording of a design that ignored the variant."""
    return run_recorded(
        tmp_path, task, ROOT / "tests" / "fixtures" / "recordings" / f"{task}_ignored.jsonl"
    )


@pytest.mark.slow
def test_a_tight_step_budget_stops_the_loop_without_a_design(gemini_loaded, tmp_path):
    """With 7 steps the designer cannot optimise: the loop says so and presents no design.

    NOTE: slow, because the designer simulates and checks a year in each round.
    """
    recording = evals.ROOT / "recordings" / "challenge2" / "tight_budget.jsonl"
    outcome = run_recorded(tmp_path, "tight_budget", recording)
    assert outcome.problems == []
    assert "No design passed" in outcome.answer
    assert "optimize" not in outcome.tools


@pytest.mark.slow
def test_a_design_that_ignores_the_cooling_peak_fails_its_checks(gemini_loaded, tmp_path):
    """The unsized plant on the 15 MW case fails gemini's checks and is rejected.

    NOTE: slow, because the design is simulated over the year.
    """
    outcome = run_ignored(tmp_path, "more_cooling")
    assert outcome.verdict["passed"] is False
    assert any(problem.startswith("verified") for problem in outcome.problems)
    assert "stop: repeated_failure" in outcome.answer
    assert "cold_delivered" in outcome.answer
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
BASE = "hackathon"
VARIANTS = ("more_cooling", "colder_reservoir", "higher_gas", "user_profile")
LAYOUT = ("case.json", "economics.json", "data/demand.csv")


def read_json_file(folder, name):
    """Return the parsed JSON file of a project."""
    return json.loads((folder / name).read_text())


@pytest.mark.parametrize("project", [BASE, "hackathon_plant", "shallow_district", *VARIANTS])
def test_each_eval_project_is_a_gemini_project_that_loads(gemini_loaded, project):
    """The workspace reads the folder's case with the files it names, and gemini builds the case."""
    data, files = FileWorkspace(PROJECTS).case(project)
    assert set(files) == {"economics.json", "data/demand.csv"}
    case = gemini_loaded.Case.from_dict(data, files=files)
    assert case.check() == []


@pytest.mark.parametrize(
    ("example", "project", "plants"),
    [
        ("hackathon_2026", BASE, 6),
        ("hackathon_2026", "hackathon_plant", 1),
        ("shallow_district", "shallow_district", 1),
    ],
)
def test_the_copies_of_gemini_s_examples_are_byte_equal(example, project, plants):
    """The copies keep the example's case, economics, demand and plant files."""
    source = example_folder(example)
    for name in (
        *LAYOUT,
        *(f"plants/{path.name}" for path in (PROJECTS / project / "plants").glob("*")),
    ):
        assert (PROJECTS / project / name).read_bytes() == (source / name).read_bytes()
    assert len(list((PROJECTS / project / "plants").glob("*.json"))) == plants


def test_the_variants_differ_from_gemini_s_example_only_by_their_variant(gemini_loaded):
    """Each variant changes one thing of the example: cooling, a gradient, a gas price."""
    import pandas as pd

    source = example_folder("hackathon_2026")
    base = pd.read_csv(source / "data" / "demand.csv")
    peak = pd.read_csv(PROJECTS / "more_cooling" / "data" / "demand.csv")
    assert peak["heating_demand_MWth"].equals(base["heating_demand_MWth"])
    assert (peak["cooling_demand_MWcool"] - 1.5 * base["cooling_demand_MWcool"]).abs().max() < 1e-3
    assert round(peak["cooling_demand_MWcool"].max(), 6) == 15.0
    assert not list((PROJECTS / "more_cooling").glob("plants"))

    colder = read_json_file(PROJECTS / "colder_reservoir", "case.json")
    expected = read_json_file(source, "case.json")
    expected["site"]["ground"]["gradient"]["value"] = 25
    assert colder == expected
    gas = read_json_file(PROJECTS / "higher_gas", "economics.json")
    expected = read_json_file(source, "economics.json")
    expected["energy"]["gas"]["value"] = gas["energy"]["gas"]["value"]
    assert gas == expected
    assert (
        gas["energy"]["gas"]["value"]
        > read_json_file(source, "economics.json")["energy"]["gas"]["value"]
    )


def test_the_user_profile_project_is_30_days_of_the_users_demand(gemini_loaded):
    """The January project ends on 2027-01-31, has 30 daily rows and no days-of-operation limit."""
    import pandas as pd

    data, files = FileWorkspace(PROJECTS).case("user_profile")
    assert data["time"]["end"] == "2027-01-31"
    assert "running_time_limit" not in {item["name"] for item in data["requirements"]}
    frame = pd.read_csv(PROJECTS / "user_profile" / "data" / "demand.csv")
    assert len(frame) == 30
    assert frame["cooling_demand_MWcool"].eq(5.0).all()
    assert gemini_loaded.Case.from_dict(data, files=files).check() == []


@pytest.fixture(scope="module")
def raw_plant_verdicts(gemini_loaded):
    """Return the verdict of gemini's heat pump plant, unsized, on the base and the 15 MW case."""
    import geomind as gd

    plant = gemini_loaded.Plant.from_dict(
        read_json_file(PROJECTS / BASE / "plants", "HeatingHeatPumpCoolingPlant.json")
    )
    verdicts = {}
    for project in (BASE, "more_cooling"):
        data, files = FileWorkspace(PROJECTS).case(project)
        case = gemini_loaded.Case.from_dict(data, files=files)
        verdicts[project] = gd.verify.verify(plant, gemini_loaded.simulate(plant, case), case)
    return verdicts


def test_the_plant_passes_its_case_and_fails_the_cooling_peak(raw_plant_verdicts):
    """The eval plant is verified on the base case and fails the 15 MW cooling peak."""
    assert raw_plant_verdicts[BASE]["passed"] is True
    peak = raw_plant_verdicts["more_cooling"]
    assert peak["passed"] is False
    assert {item["name"] for item in peak["failures"]} >= {"cold_delivered"}

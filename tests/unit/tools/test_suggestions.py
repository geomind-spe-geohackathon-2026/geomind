"""Next-step suggestions: the stage by code, English only, the lead's own list checked."""

from pathlib import Path

import pytest

import geomind as gd
from geomind.agents import Agent, Model
from geomind.context import ProblemState
from geomind.engine import Engine
from geomind.prompts import Prompt
from geomind.stores import MemoryWorkspace
from geomind.stores.run import FileRunStore
from geomind.tools import suggestions
from geomind.tools.suggestions import MAX_LABEL, MAX_MESSAGE, next_steps, stage_of
from geomind.types.events import event_from_dict
from tests.fixtures.runs import Lead, Worker, call, context, engine_for, of_type, says, uses

OLD_LOG = Path(__file__).parents[2] / "fixtures" / "logs" / "mcp_0_4_22_dev41"
CASE = {"name": "c", "economics": {"discount_rate": 0.05}}
PLANT = ProblemState(case=CASE, design={"reference": "design/a"})
RESULT = ProblemState(case=CASE, design={"reference": "design/a", "result": "result/a"})


@pytest.mark.parametrize(
    ("problem", "stage"),
    [
        (ProblemState(), "no_case"),
        (ProblemState(case=CASE), "case"),
        (PLANT, "plant"),
        (RESULT, "result"),
        ({"case": CASE, "design": {}, "results": []}, "case"),
    ],
)
def test_the_stage_comes_from_the_problem_state(problem, stage):
    """No case, a case without a plant, a plant without a result, a result."""
    assert stage_of(problem) == stage


def test_each_stage_gives_its_steps_and_no_case_from_files_without_files():
    """A chat with files may build its case from them; one without may not."""
    labels = [item["label"] for item in next_steps(ProblemState(), ["brief.pdf"], "go")]
    assert labels[0] == "Build the case from my files" and len(labels) == 3
    without = [item["label"] for item in next_steps(ProblemState(), [], "go")]
    assert "Build the case from my files" not in without and len(without) == 2
    assert [item["label"] for item in next_steps(RESULT, [], "go")] == [
        "Write the report",
        "Sensitivity analysis",
        "Explain the results",
    ]


PERSIAN_QUESTION = (
    "\u0647\u0632\u06cc\u0646\u0647 \u0686\u0642\u062f\u0631 \u0627\u0633\u062a\u061f"
)
"""A question in Persian, written escaped: no file holds Persian text (Sahand, 2026-11-04)."""


def test_suggestions_are_english_whatever_the_user_writes():
    """Arabic script in the user's last message: the labels stay English (Sahand, 2026-11-04)."""
    assert next_steps(PLANT, [], PERSIAN_QUESTION) == next_steps(PLANT, [], "go")


def test_every_step_fits_the_limits():
    """Each built-in label and message fits; each stage names known steps."""
    for texts in suggestions.STEPS.values():
        for label, message in texts.values():
            assert 0 < len(label) <= MAX_LABEL and 0 < len(message) <= MAX_MESSAGE
    staged = {step for steps in suggestions.STAGES.values() for step in steps}
    assert staged | {"rerun_study", "wait_study", "finish_item", "set_economics"} == set(suggestions.STEPS)


def test_the_lead_may_reword_and_reorder():
    """A list that fits is kept, in its order."""
    proposed = [
        {"step": "check_design", "label": "Check it first", "message": "Check the design now."},
        {"step": "optimise", "label": "Then optimise", "message": "Optimise the design."},
    ]
    assert next_steps(PLANT, [], "go", proposed) == [
        {"label": "Check it first", "message": "Check the design now."},
        {"label": "Then optimise", "message": "Optimise the design."},
        suggestions.shown("economics"),
    ]


@pytest.mark.parametrize(
    "item",
    [
        {"step": "launch_rocket", "label": "Go", "message": "Go."},
        {"step": "optimise", "label": "x" * (MAX_LABEL + 1), "message": "Go."},
        {"step": "optimise", "label": "Go", "message": "x" * (MAX_MESSAGE + 1)},
        {"step": "optimise", "label": "", "message": "Go."},
        {"step": "optimise", "label": "\u0628\u0647\u06cc\u0646\u0647", "message": "Go."},
        "optimise",
    ],
)
def test_a_suggestion_that_does_not_fit_falls_back_to_the_stage(item):
    """An unknown step, a long or empty text, another script: the stage's own list."""
    assert next_steps(PLANT, [], "go", [item]) == next_steps(PLANT, [], "go")


def test_at_most_three_and_one_step_from_outside_the_stage():
    """The lead replaces one step at most; a fourth suggestion is cut."""
    proposed = [
        {"step": "report", "label": "Report", "message": "Write the report."},
        {"step": "explain", "label": "Explain", "message": "Explain it."},
        {"step": "optimise", "label": "Optimise", "message": "Optimise it."},
        {"step": "economics", "label": "Costs", "message": "Estimate the costs."},
        {"step": "check_design", "label": "Check", "message": "Check it."},
    ]
    labels = [item["label"] for item in next_steps(PLANT, [], "go", proposed)]
    assert labels == ["Report", "Optimise", "Costs"]


def test_the_end_to_end_finish_keeps_one_step_from_outside_the_case_stage():
    """#128: the lead's finish had three items, run.finished two, by the stage's rule.

    The stage was ``case``: ``case_by_questions`` is its one step from outside, ``other_case`` (a
    "more" step) a second one, dropped; the event holds ``{label, message}`` only, as the contract.
    """
    recorded = [
        {
            "step": "case_by_questions",
            "label": "Provide site air pressure",
            "message": "site.air.pressure: <value> <unit>",
        },
        {
            "step": "design_plant",
            "label": "Retry design after pressure set",
            "message": "Once site.air.pressure is set, run the design again.",
        },
        {
            "step": "other_case",
            "label": "Change the case",
            "message": "I want to change something else in the case.",
        },
    ]
    found = next_steps(ProblemState(case=CASE), [], "Design a plant", recorded)
    kept = [{key: item[key] for key in ("label", "message")} for item in recorded[:2]]
    assert found == [*kept, suggestions.shown("check_case")]
    assert "other_case" not in suggestions.STAGES["case"]


def test_gd_suggest_serves_an_empty_chat_without_a_model():
    """The backend calls it before the first message; English for an empty chat."""
    assert gd.suggest(ProblemState(), ["brief.pdf"])[0]["label"] == "Build the case from my files"
    assert gd.suggest({"case": CASE, "design": {}, "results": []}, [])[0]["label"] == (
        "Design a plant"
    )
    assert "suggest" in gd.__all__


class Leader(Agent):
    """An agent whose finish takes suggestions, as the project lead's does."""

    def __init__(self):
        """Declare the finish."""
        super().__init__()
        self.prompt = Prompt.text("Answer.")
        self.finish = suggestions.finish
        self.model = Model("fake/model")


async def finished(completions, agent, text="go", **options):
    """Run a script; return the root run's ``run.finished`` event."""
    engine = engine_for(completions, **options)
    start = context(text)
    await engine.run(agent, start)
    return of_type(engine.store.load_events(start.run_id), "run.finished")[0]


async def test_a_root_run_that_ends_done_carries_the_stage_s_steps():
    """No case and no files: build the case by questions, or name the files."""
    event = await finished([says("Hello")], Worker())
    assert [item["label"] for item in event.data()["suggestions"]] == [
        "Build the case by questions",
        "Which files do you need?",
    ]


async def test_the_lead_s_finish_suggestions_reach_the_event():
    """The project lead's own list, checked, is the one the app shows."""
    proposed = [{"step": "files_needed", "label": "Send files", "message": "What files?"}]
    script = [uses(call("finish", answer="Hi", suggestions=proposed))]
    event = await finished(script, Leader())
    assert event.data()["suggestions"] == [
        {"label": "Send files", "message": "What files?"},
        suggestions.shown("case_by_questions"),
    ]


async def test_a_project_s_files_offer_the_case_from_files():
    """The workspace's files reach the stage."""
    workspace = MemoryWorkspace(files={"p": {"brief.pdf": b"%PDF-1.4"}})
    engine = engine_for([says("Hello")], workspace=workspace)
    start = context("go", project="p")
    await engine.run(Worker(), start)
    [event] = of_type(engine.store.load_events(start.run_id), "run.finished")
    assert event.suggestions[0]["label"] == "Build the case from my files"


async def test_a_nested_run_a_waiting_run_and_a_failed_run_have_none():
    """Only the root run's ``done`` ends with suggestions."""
    engine = engine_for([uses(call("helper", task="t")), says("child done"), says("done")])
    start = context()
    await engine.run(Lead(), start)
    events = [e for run in engine.store.events.values() for e in run if e.type == "run.finished"]
    child = [event for event in events if event.parent is not None]
    assert child and all("suggestions" not in event.data() for event in child)
    waiting = engine_for([uses(call("ask_user", question="Which?"))])
    start = context()
    result = await waiting.run(Worker(), start)
    assert result.status == "waiting"
    assert of_type(waiting.store.load_events(start.run_id), "run.finished") == []
    failed = await finished([uses(call("nothing_here")), uses(call("nothing_here"))] * 3, Worker())
    assert failed.status == "failed" and "suggestions" not in failed.data()


async def test_the_run_result_carries_the_run_finished_suggestions(monkeypatch):
    """Contract v5: a root ``done`` result has its event's list; nested, waiting, failed none."""
    engine = engine_for([says("Hello")])
    start = context()
    result = await engine.run(Worker(), start)
    [event] = of_type(engine.store.load_events(start.run_id), "run.finished")
    assert result.suggestions and result.suggestions == event.suggestions
    ends = []
    end = Engine.end

    async def recorded(self, session, stop):
        outcome = await end(self, session, stop)
        ends.append((session.state.parent, outcome))
        return outcome

    monkeypatch.setattr(Engine, "end", recorded)
    engine = engine_for([uses(call("helper", task="t")), says("child done"), says("done")])
    root = await engine.run(Lead(), context())
    children = [outcome for parent, outcome in ends if parent is not None]
    assert root.suggestions and children and all(c.suggestions is None for c in children)
    waiting = await engine_for([uses(call("ask_user", question="Which?"))]).run(Worker(), context())
    assert waiting.status == "waiting" and waiting.suggestions is None
    script = [uses(call("nothing_here")), uses(call("nothing_here"))] * 3
    failed = await engine_for(script).run(Worker(), context())
    assert failed.status == "failed" and failed.suggestions is None


def test_an_old_run_finished_has_no_suggestions():
    """A log before 0.4.22.dev48 has none, and its data leaves the key out."""
    event = event_from_dict(
        {"type": "run.finished", "run_id": "r", "status": "done", "stop_reason": "finish"}
    )
    assert event.suggestions is None and "suggestions" not in event.data()


async def test_an_old_log_replays_with_its_answer():
    """The replay of a dev41 log compares the answer, not the new field."""
    store = FileRunStore(OLD_LOG)
    [run_id] = [path.name for path in OLD_LOG.iterdir()]
    replayed = await Engine.replay(store, run_id, workspace=MemoryWorkspace())
    assert replayed.answer == "TTF is 31.5 EUR/MWh"


async def test_a_replayed_run_gives_the_same_suggestions():
    """The suggestions come from the log by code, so a replay makes them again alike."""
    proposed = [{"step": "files_needed", "label": "Send files", "message": "What files?"}]
    engine = engine_for([uses(call("finish", answer="Hi", suggestions=proposed))])
    start = context()
    await engine.run(Leader(), start)
    replayed_events = []
    await Engine.replay(engine.store, start.run_id, replayed=replayed_events)
    [recorded] = of_type(engine.store.load_events(start.run_id), "run.finished")
    replayed = [e for e in replayed_events if e.type == "run.finished" and e.parent is None]
    assert replayed and replayed[0].suggestions == recorded.suggestions


DONE = {"case": "done", "plant": "done", "study": "done", "results": "done"}


def project(**parts):
    """Return a project state: every part done but those given, the report done."""
    state = {**DONE, "report": {"state": "done", "label": "report"}}
    state.update(parts)
    return state


def labels(project_state, files=(), text="go", problem=None):
    """Return the labels the project's state gives after an answer."""
    chat = problem or ProblemState()
    return [item["label"] for item in next_steps(chat, list(files), text, project=project_state)]


def test_a_project_without_a_done_case_builds_one():
    """Stage 1, from the files when there are some."""
    assert labels(project(case="empty"), ["brief.pdf"])[0] == "Build the case from my files"


def test_a_new_chat_in_a_project_with_a_case_never_builds_one():
    """The chat's own state is empty, but the project has its case: stage 2."""
    found = labels(project(plant="empty", study="empty", results="empty"))
    assert found[0] == "Design a plant" and not any("Build the case" in item for item in found)


def test_a_plant_ready_or_done_goes_to_the_study():
    """A plant that is ready counts: optimise, economics, check."""
    assert (
        labels(project(plant="ready", study="empty", results="empty"))[0] == "Optimise the design"
    )


def test_a_running_study_offers_waiting_and_no_new_study():
    """No study chip while one runs: wait for it or explain."""
    found = labels(project(study="running", results="empty"))
    assert found[:2] == ["Is the study done?", "Explain the results"]
    assert "Optimise the design" not in found


def test_a_report_not_done_is_stage_four():
    """Report, explain, sensitivity."""
    found = labels(project(report={"state": "empty", "label": "report"}))
    assert found == ["Write the report", "Explain the results", "Sensitivity analysis"]


def test_an_incomplete_item_is_finished_first_by_its_label():
    """An incomplete report: finish it, by the label the backend gives."""
    found = labels(project(report={"state": "incomplete", "label": "cost report"}))
    assert found[0] == "Finish the cost report"
    persian = labels(
        project(report={"state": "incomplete", "label": "cost report"}), text=PERSIAN_QUESTION
    )
    assert persian[0] == "Finish the cost report"


def test_all_done_offers_more_studies():
    """Uncertainty, another plant layout by structure search, another objective."""
    assert labels(project()) == [
        "Uncertainty of the results",
        "Search other plant layouts",
        "Optimise for CO2 instead",
    ]


def test_a_case_changed_after_the_study_asks_for_the_study_again_first():
    """The stale study comes before everything else."""
    assert labels(project(case_changed_after_study=True))[0] == "Run the study again"


def test_gd_suggest_takes_the_project_state():
    """An empty chat in a finished project offers more studies, not a case."""
    assert gd.suggest(ProblemState(), [], project=project())[0]["label"] == (
        "Uncertainty of the results"
    )


def test_the_folder_workspace_reads_the_project_state(tmp_path):
    """case.json newer than the newest study: the study is stale; no report: empty."""
    import os

    from geomind.stores import FileWorkspace

    folder = tmp_path / "p"
    (folder / "studies").mkdir(parents=True)
    (folder / "plants").mkdir()
    (folder / "plants" / "a.json").write_text("{}")
    (folder / "studies" / "s.json").write_text("{}")
    (folder / "case.json").write_text("{}")
    os.utime(folder / "studies" / "s.json", ns=(1, 1))
    state = FileWorkspace(tmp_path).project_state("p")
    assert (state["case"], state["plant"], state["study"], state["results"]) == (
        "done",
        "done",
        "done",
        "empty",
    )
    assert state["report"] == {"state": "empty", "label": "report"}
    assert state["case_changed_after_study"] is True
    assert FileWorkspace(tmp_path).project_state("none") is None


class ProjectWorkspace(MemoryWorkspace):
    """A workspace whose project has its case, as the backend's does."""

    def project_state(self, project_id):
        """Return a project with a case and nothing more."""
        return project(plant="empty", study="empty", results="empty")


async def test_a_run_s_suggestions_follow_the_workspace_s_project_state():
    """The chat has no case, the project has one: no case is built again."""
    engine = engine_for([says("Hello")], workspace=ProjectWorkspace())
    start = context("go", project="p")
    await engine.run(Worker(), start)
    [event] = of_type(engine.store.load_events(start.run_id), "run.finished")
    assert event.suggestions[0]["label"] == "Design a plant"


def test_one_proposed_step_keeps_the_stage_s_others():
    """QA-204: the lead's one step comes first; the stage's own fill the list to three."""
    proposed = [{"step": "explain", "label": "Explain it", "message": "Explain the result."}]
    assert [item["label"] for item in next_steps(RESULT, [], "go", proposed)] == [
        "Explain it",
        "Write the report",
        "Sensitivity analysis",
    ]


def test_a_case_without_economics_asks_for_them_first():
    """QA-194: a ready case with no economics offers them before a plant, chat or project."""
    bare = ProblemState(case={"name": "c"})
    assert next_steps(bare, [], "go")[0]["label"] == "Set the economics"
    assert next_steps(ProblemState(case=CASE), [], "go")[0]["label"] == "Design a plant"
    state = project(plant="empty", study="empty", results="empty", economics="empty")
    assert labels(state)[0] == "Set the economics"
    assert labels({**state, "economics": "done"})[0] == "Design a plant"

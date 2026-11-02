"""The usage ledgers: what the finished runs of a project spent."""

import geomind as gd
from geomind.engine.hooks import ProjectBudget
from geomind.providers import FakeLLM
from geomind.stores import FileRunStore, FileUsageLedger, MemoryUsageLedger
from geomind.types import Usage
from tests.fixtures.runs import Lead, Worker, call, logged, same_usage, says, uses


def finish(root, project, script, agent=None, **options):
    """Run one root run of a project to its end on a file store; return its run."""
    run = gd.Run(
        message="go",
        project=project,
        agent=agent or Worker(),
        llm=FakeLLM(script),
        store=FileRunStore(root),
        **options,
    )
    run.start()
    return run


def test_memory_ledger_sums_by_project():
    """An unknown project spent nothing."""
    ledger = MemoryUsageLedger()
    ledger.add("p", Usage(input_tokens=3, cost=0.5))
    ledger.add("p", Usage(output_tokens=2, cost=0.25))
    assert ledger.spent("p") == Usage(input_tokens=3, output_tokens=2, cost=0.75)
    assert ledger.spent("other") == Usage()


def test_file_ledger_of_a_missing_root_is_empty(tmp_path):
    """Nothing stored, nothing spent."""
    assert FileUsageLedger(tmp_path / "nope").spent("p") == Usage()


def test_file_ledger_sums_the_finished_root_runs_of_the_project(tmp_path):
    """Two runs of the project add up; another project's run does not."""
    finish(tmp_path, "p", [says("a")])
    finish(tmp_path, "p", [says("b")])
    finish(tmp_path, "q", [says("c")])
    spent = FileUsageLedger(tmp_path).spent("p")
    assert spent == Usage(input_tokens=20, output_tokens=10, cost=0.02)


def test_file_ledger_counts_a_run_with_nested_runs_once(tmp_path):
    """The tree's usage is the root run's; nested runs are not summed again."""
    script = [
        uses(call("helper", task="t")),
        says("found"),
        says("end"),
    ]
    run = finish(tmp_path, "p", script, agent=Lead())
    events = FileRunStore(tmp_path).load_events(run.id)
    assert any(e.parent is not None for e in events)
    assert same_usage(FileUsageLedger(tmp_path).spent("p"), logged(events))


def test_file_ledger_skips_unfinished_runs(tmp_path):
    """A run that waits for an answer has not finished and does not count."""
    finish(tmp_path, "p", [uses(call("ask_user", question="which?"))])
    assert FileUsageLedger(tmp_path).spent("p") == Usage()


def test_file_ledger_ignores_chats_and_other_files(tmp_path):
    """The chats folder and stray folders are not runs."""
    store = FileRunStore(tmp_path)
    store.save_state("chat", {"a": 1})
    (tmp_path / "stray").mkdir()
    finish(tmp_path, "p", [says("a")])
    assert FileUsageLedger(tmp_path).spent("p").input_tokens == 10


def test_a_resumed_run_counts_once(tmp_path):
    """Paused, a run is not in the ledger; its steps count once, by the budget's session.

    The first leg used 15 tokens. A cap of 25 allows the second call only if the 15 are not
    counted twice; once the run ends, the ledger holds it.
    """
    ledger = FileUsageLedger(tmp_path)
    script = [uses(call("ask_user", question="which?")), says("end")]
    run = gd.Run(
        message="go",
        project="p",
        agent=Worker(),
        llm=FakeLLM(script[:1]),
        store=FileRunStore(tmp_path),
    )
    paused = run.start()
    assert ledger.spent("p") == Usage()
    budget = ProjectBudget(ledger, "p", max_tokens=25)
    fresh = gd.Run.load(
        run.id, llm=FakeLLM(script[1:]), store=FileRunStore(tmp_path), hooks=[budget]
    )
    result = fresh.resume(paused.request.id, {"text": "this one"})
    assert (result.status, result.answer) == ("done", "end")
    spent = ledger.spent("p")
    assert spent.input_tokens + spent.output_tokens == 30

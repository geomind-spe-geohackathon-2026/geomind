"""A case through ``geomind run --loop design``, offline from a scripted recording.

NOTE: the recordings are hand-written decisions in the order the design loop asks its agents (read
the plant class and the case, build, size, simulate, check, optimise, simulate and check again,
record; check once; cost; explain); every reference and number in them comes from the real gemini
tools. They check the path from the command line to a verified, costed and explained design, not a
model.
"""

import re
from pathlib import Path

import pytest

from geomind import cli
from geomind.engine import replay
from geomind.export import render_export
from geomind.stores.run import FileRunStore
from geomind.utils.json import read_json
from tests.fixtures import ROOT
from tests.fixtures.cases import example_folder

REQUEST = (
    "Design a deep-geothermal plant for the project's case, starting from the plant class "
    "HeatingHeatPumpCoolingPlant. Size the plant with the peak backup policy (a boiler that covers "
    "the whole heating peak), then optimise the levelised cost of thermal service (objective lcts) "
    "over the plant's own ranges with 30 evaluations and seed 0."
)
RECORDINGS = {
    "hackathon_2026": ROOT / "evals" / "runs" / "hackathon_scripted.jsonl",
    "shallow_district": ROOT
    / "tests"
    / "fixtures"
    / "recordings"
    / "shallow_district_scripted.jsonl",
}
PROJECTS = {
    "hackathon_2026": ROOT / "evals" / "projects" / "hackathon",
    "shallow_district": example_folder("shallow_district"),
}


@pytest.mark.parametrize("name", RECORDINGS)
def test_a_case_gives_a_verified_design_that_replays(name, monkeypatch, tmp_path, capsys):
    """The run ends verified, with capacities, energies, costs and open points, and replays."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt: "Use the project's case.")
    arguments = ["run", REQUEST, "--loop", "design", "--mode", "auto"]
    arguments += ["--project", str(PROJECTS[name]), "--recording", str(RECORDINGS[name])]
    assert cli.main(arguments) == 0
    output = capsys.readouterr().out
    run = next(path for path in Path(".runs").iterdir() if path.name != "chats")
    assert "design loop: stop: verified after round 1" in output
    for heading in ("## Capacities", "## Delivered", "## Costs", "## Open points", "LCTS"):
        assert heading in output
    original = FileRunStore(run.parent).load_events(run.name)
    text = check_export(run)
    stores = []

    class Capturing(replay._ReplayStore):
        """Keep the store a replay writes, to read the replayed tree."""

        def __init__(self, *arguments):
            """Register this store."""
            super().__init__(*arguments)
            stores.append(self)

    monkeypatch.setattr(replay, "_ReplayStore", Capturing)
    assert cli.main(["replay", str(run), "--project", str(PROJECTS[name])]) == 0
    assert capsys.readouterr().out.startswith("pass:")
    replayed = stores[0].load_events(run.name)
    assert calls_of(replayed) == calls_of(original)
    manifest = read_json(run / "run_manifest.json")
    assert normalised(render_export(replayed, manifest)) == normalised(text)


def calls_of(events):
    """Return each step of a log with its run's agent: its completions, then its tool results.

    NOTE: the read and compute calls of one step run side by side and log their results in the
    order they finish, so a step's results are put in the order of its calls, as replay itself
    compares them; a different completion or result still differs.
    """
    runs = {e.run_id: e.agent for e in events if e.type == "run.started"}
    places = {
        (e.run_id, e.index, call.id): position
        for e in events
        if e.type == "llm.completed"
        for position, call in enumerate(e.completion.tool_calls)
    }
    steps = {}
    for e in events:
        if e.type not in ("llm.completed", "tool.result"):
            continue
        completions, results = steps.setdefault((e.run_id, e.index), ([], []))
        if e.type == "llm.completed":
            completions.append((e.completion.text, e.completion.tool_calls))
            continue
        place = places.get((e.run_id, e.index, e.call_id), len(places))
        results.append((place, e.tool, e.input, e.output))
    return [
        (runs[run], index, completions, sorted(results, key=lambda item: item[0]))
        for (run, index), (completions, results) in steps.items()
    ]


def test_results_of_one_step_compare_in_call_order():
    """Two results of one step that finished the other way round are the same step."""
    from geomind.types import Completion, ToolCall, Usage
    from geomind.types.events import LLMCompleted, RunStarted, ToolRecorded

    calls = (ToolCall(id="a", name="x", input={}), ToolCall(id="b", name="y", input={}))
    completion = Completion(text="", tool_calls=calls, usage=Usage(), model="m")
    started = RunStarted(run_id="r", sequence=1, run="r", root="r", agent_class="c", max_steps=1)

    def log(first, second, changed=""):
        return [
            started,
            LLMCompleted(run_id="r", sequence=2, index=1, completion=completion),
            ToolRecorded(run_id="r", sequence=3, index=1, call_id=first, tool=first, output=first),
            ToolRecorded(
                run_id="r",
                sequence=4,
                index=1,
                call_id=second,
                tool=second,
                output=second + changed,
            ),
        ]

    assert calls_of(log("b", "a")) == calls_of(log("a", "b"))
    assert calls_of(log("a", "b", changed="!")) != calls_of(log("a", "b"))


def normalised(text):
    """Return an export without run ids, timestamps and durations."""
    text = re.sub(r"[0-9a-f]{32}", "<id>", text)
    text = re.sub(r"\d{4}-\d\d-\d\d[T ][\d:.+Z-]+", "<time>", text)
    return text


def check_export(run):
    """Check that the export holds every part in order, and return it."""
    events = FileRunStore(run.parent).load_events(run.name)
    manifest = read_json(run / "run_manifest.json")
    text = render_export(events, manifest)
    parts = ["## Request", "Models by role:", "## LLM calls", "## Appendix: system prompts"]
    parts += ["## Tokens by agent", "## Tokens by step", "## Totals"]
    positions = [text.index(part) for part in parts]
    assert positions == sorted(positions)
    assert f"gemini version: {manifest['gemini']['version']}" in text
    assert text.count("### Call ") == text.count("Tokens: ") == 19
    for agent in ("designer", "verifier", "economist", "explainer"):
        assert text.count(f"### {agent}\n") == 1
    assert "- build_plant(" in text and "(0 cached)" in text
    return text

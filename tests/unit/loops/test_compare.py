"""``StudyCompareLoop``: a design loop whose designer compares families with one ``run_study``.

The loop runs once, offline, on the hackathon example with real tools: a scripted designer builds
two feasible topologies, sizes and searches them, and records the study; the verifier, economist
and explainer steps follow.
"""

import ast
import asyncio
import re

import pytest

from geomind import runtime
from geomind.agents import Designer, Verifier
from geomind.agents.coordination.coordinator import Route
from geomind.context import ProblemState
from geomind.engine import Engine, Permissions
from geomind.engine.recovery import recover
from geomind.loops import CompareLoop, DesignLoop, StudyCompareLoop
from geomind.loops.design import study_table
from geomind.providers import FakeLLM
from geomind.run import LOOPS, loop_of
from geomind.types import ToolCall
from tests.fixtures.cases import example_case, example_plant, warm_gemini
from tests.fixtures.runs import STEPS, context, of_type, says, uses

NAME = "hackathon_2026"
FAMILIES = ("HeatingAbsorptionCoolingPlant", "HeatingCoolingPlant")
SEARCH = {"objective": "lcts", "evaluations": 5, "seed": 1}
RESULT = re.compile(r"result/\w+")


STORED = {}


class Steps(FakeLLM):
    """A scripted provider whose entries may be functions of the agent's messages.

    A function entry gets the messages of the call and returns the completion, so a step can use
    the reference a tool returned before.
    """

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Resolve a function entry from the messages, then answer as ``FakeLLM`` does."""
        position = len(self.calls)
        if position < len(self.completions) and callable(self.completions[position]):
            self.completions[position] = self.completions[position](messages)
        return await super().complete(
            messages, tools, model=model, settings=settings, on_text=on_text
        )


def output_of(messages, call_id):
    """Return the output of one tool call; an old one is read from its stored reference."""
    text = next(item.content for item in messages if item.tool_call_id == call_id)
    found = ast.literal_eval(text)
    if isinstance(found, dict) and str(found.get("reference", "")).startswith("result-"):
        return STORED["store"].load_chat_artifact(STORED["chat"], found["reference"])
    return found


def reference_of(messages):
    """Return the result reference named in the task of the agent."""
    task = next(item.content for item in messages if item.role == "user")
    return RESULT.search(task).group()


def step(tool, call_id, **arguments):
    """Return a completion that makes one tool call."""
    return uses(ToolCall(id=call_id, name=tool, input=arguments))


def only_doublets(name):
    """Return the plant file of a hackathon plant class with just the doublets as a range."""
    plant = example_plant(NAME, name)
    for path in list(plant.ranges):
        plant.set_range(path, None, None)
    file = plant.to_dict(structure=True)
    file["params"]["backup"] = {"value": "peak"}
    return file


def best_of(study):
    """Return the stored design of the run ranked first on the objective."""
    return next(run["design"] for run in study["runs"] if run["ranks"]["lcts"] == 1)


def assumptions():
    """Return the update of the state that records what the designer chose itself."""
    chosen = [("peak backup keeps heat at a doublet outage", "peak"), ("search seed", 1)]
    return [
        {
            "op": "add",
            "path": "/assumptions/-",
            "value": {"id": f"A{index}", "text": text, "value": value, "source": "agent"},
        }
        for index, (text, value) in enumerate(chosen, start=1)
    ]


def record(messages):
    """Return the designer's update of the state: the final design, the start and the study."""
    study = output_of(messages, "study")
    columns = ("design", "feasible", "ranks", "metrics")
    recorded = {"designs": ["design/ra", "design/rb"], "method": "minimize", **SEARCH}
    recorded["runs"] = [{key: run[key] for key in columns} for run in study["runs"]]
    start = output_of(messages, "start")["reference"]
    value = {
        "reference": best_of(study),
        "result": output_of(messages, "year")["reference"],
        "start_result": start,
        "alternatives": [{"family": "B", "design": "design/rb", "result": start}],
        "study": recorded,
    }
    return step(
        "update_state", "design", changes=[{"op": "replace", "path": "/design", "value": value}]
    )


def designer_script():
    """Return the designer's completions: two families, a study, the best simulated and recorded."""
    ranges = {"ranges": {"size.doublets": {"min": 1, "max": 2}}}
    both = ["design/ra", "design/rb"]
    return [
        step("read_case", "case"),
        step("build_plant", "a", plant=only_doublets(FAMILIES[0]), name="a"),
        step("build_plant", "b", plant=only_doublets(FAMILIES[1]), name="b"),
        step("set_ranges", "ra", design="design/a", name="ra", **ranges),
        step("set_ranges", "rb", design="design/b", name="rb", **ranges),
        step("size_plant", "sized", design="design/ra", name="sized"),
        step("simulate", "start", design="design/sized"),
        step("update_state", "notes", changes=assumptions()),
        step(
            "run_study",
            "study",
            designs=both,
            method="minimize",
            prepare=["size"],
            name="families",
            **SEARCH,
        ),
        lambda messages: step("simulate", "year", design=best_of(output_of(messages, "study"))),
        lambda messages: step(
            "check_results", "own", reference=output_of(messages, "year")["reference"]
        ),
        record,
        says("compared two families"),
    ]


def verifier_script():
    """Return the verifier's completions: check the recorded result once, record, report."""

    def check(messages):
        return step("check_results", "v1", reference=reference_of(messages))

    def report(messages):
        found = output_of(messages, "v1")
        value = {
            "result": reference_of(messages),
            "passed": found["feasible"],
            "failures": found["failures"],
        }
        change = {"op": "replace", "path": "/verification", "value": value}
        return step("update_state", "v2", changes=[change])

    return [check, report, says("passed: gemini's verdict is feasible. case unchanged.")]


def economist_script():
    """Return the economist's completions: cost the verified result, report."""

    def cost(messages):
        return step("estimate_costs", "k1", reference=reference_of(messages))

    return [cost, says("costs reported")]


async def run_compare():
    """Run the compare loop once on the hackathon example; return ``(result, events)``."""
    data, files = example_case(NAME)
    script = [*designer_script(), *verifier_script(), *economist_script(), says("explained")]
    engine = Engine(llm=Steps(script), permissions=Permissions(mode="auto"))
    start = context("Compare alternative plants for the case.", problem=ProblemState(case=data))
    STORED.update(store=engine.store, chat=start.run_id)
    for file, content in files.items():
        engine.store.save_chat_artifact(start.run_id, f"case/{file}", content)
    result = await StudyCompareLoop(Designer(), Verifier()).run(engine, start)
    return result, engine.store.load_events(start.run_id)


@pytest.fixture(scope="module")
def compared():
    """Run the loop once for the module: it simulates and searches."""
    warm_gemini()
    with runtime.settings(max_steps=STEPS):
        return asyncio.run(run_compare())


def task_of(events, agent):
    """Return the first task the loop gave an agent."""
    return next(e.messages[0].content for e in of_type(events, "run.started") if e.agent == agent)


def test_the_loop_is_a_named_design_loop():
    """It is a design loop of its own name, with a driver that asks for several families."""
    loop = StudyCompareLoop(Designer(), Verifier())
    assert isinstance(loop, DesignLoop) and loop.name == "compare"
    assert type(loop.agent).__name__ == "CompareDriver"


def test_the_designer_is_asked_to_compare_families(compared):
    """The first task names the comparison and what to record."""
    task = task_of(compared[1], "designer")
    assert "two or three materially different families" in task
    assert "run_study" in task and "design.study" in task


def test_the_study_ranks_the_families_and_the_best_is_verified(compared):
    """One study ran; its best design passed gemini's verdict and the loop went on to the end."""
    result, events = compared
    problem = recover(events).problem
    study = problem.design["study"]
    assert result.status == "done" and "stop: verified" in result.answer
    assert problem.verification["passed"] is True
    assert len(study["runs"]) == 2 and study["method"] == "minimize"
    assert problem.design["reference"] == best_of(study)


def test_the_table_of_the_study_reaches_the_explainer(compared):
    """The explainer's task carries the ranked table of the designer's study."""
    events = compared[1]
    table = study_table(recover(events).problem.design["study"])
    assert "| design | feasible | rank | lcts |" in table
    assert table in task_of(events, "explainer")


def test_the_economist_is_told_of_the_study(compared):
    """The economist's task points to design.study."""
    assert "design.study" in task_of(compared[1], "economist")


def test_a_route_to_compare_builds_the_loop():
    """The table, the route and the loop agree."""
    assert LOOPS["compare"] is CompareLoop
    assert "compare" in Route.model_fields["loop"].annotation.__args__
    assert isinstance(loop_of(Route(kind="loop", loop="compare")), CompareLoop)

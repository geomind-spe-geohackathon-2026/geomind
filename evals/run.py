"""Run the tasks of one agent and report: ``python -m evals.run --agent analyst [--live]``.

Offline by default, from ``recordings/``. ``--live`` calls OpenRouter and writes the recording.
Criteria are checked by code, never by an LLM. A suite of ``SUITES`` (``challenge2``) runs its
tasks through a loop instead of one agent.
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

import geomind as gd
from evals.tasks_format import VerifiedCriterion, load_task
from geomind.agents import Route
from geomind.context import ProblemState
from geomind.engine import Context
from geomind.providers import FakeLLM, OpenRouter, Recorder
from geomind.run import loop_of
from geomind.stores import FileWorkspace, MemoryRunStore
from geomind.types import Usage

ROOT = Path(__file__).parent
CHAT = "eval"
SUITES = {"challenge2": "design"}
"""Task folders run through a loop rather than one agent: the folder name and its loop."""


@dataclass
class Outcome:
    """What one task did, and what the criteria found."""

    name: str
    answer: str = ""
    tools: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    state: dict = field(default_factory=dict)
    steps: int = 0
    usage: Usage = Usage()
    time: float = 0.0
    problems: list = field(default_factory=list)
    verdict: dict = field(default_factory=dict)

    @property
    def passed(self):
        """Tell whether every criterion held."""
        return not self.problems


def _workspace(task):
    """Return the workspace and the project of a task."""
    if task.plant is None:
        return None, None
    folder = Path(task.plant)
    return FileWorkspace(folder.parent), folder.name


def _drive(run, answers):
    """Start the run and reply to its questions; a question with no reply left ends it."""
    replies = list(answers)
    result = run.start()
    while result.status == "waiting" and replies:
        result = run.resume(result.request.id, {"text": replies.pop(0)})
    return result


class StoredArtifacts:
    """The artifacts of one stored run, read as a session reads them."""

    def __init__(self, store, run_id):
        """Keep the store and the run."""
        self.store = store
        self.run_id = run_id

    def load_artifact(self, key):
        """Return an artifact of the run, or ``None``."""
        return self.store.load_artifact(self.run_id, key)


def verdict(store, run_id, state):
    """Return gemini's checks on the final state's design and result, as ``verify_design``."""
    from geomind.verify.design import verify_design

    context = Context(
        problem=ProblemState.model_validate(state), session=StoredArtifacts(store, run_id)
    )
    return verify_design(context)


def new_run(task, agent_name, llm, store):
    """Return the run of a task: one agent, or the loop of a suite."""
    workspace, project = _workspace(task)
    run = gd.Run(
        task.message,
        chat=CHAT,
        project=project,
        history=task.history,
        llm=llm,
        store=store,
        workspace=workspace,
        permissions=gd.Permissions(mode="auto"),
        agent=None if agent_name in SUITES else gd.agents.named(agent_name),
    )
    if agent_name in SUITES:
        run.loop = loop_of(Route(kind="loop", loop=SUITES[agent_name]))
    return run


def run_task(name, task, agent_name, llm):
    """Run one task and return its outcome."""
    store = MemoryRunStore()
    run = new_run(task, agent_name, llm, store)
    started = perf_counter()
    result = _drive(run, task.answers)
    events = store.load_events(result.run_id)
    outcome = Outcome(
        name=name,
        answer=str(result.answer or ""),
        tools=[e.tool for e in events if e.type == "tool.result" and e.call_id],
        questions=[e.request.message for e in events if e.type == "request"],
        state=store.load_state(CHAT) or {},
        steps=result.steps,
        usage=result.usage,
        time=perf_counter() - started,
    )
    if any(isinstance(criterion, VerifiedCriterion) for criterion in task.criteria):
        outcome.verdict = verdict(store, result.run_id, outcome.state)
    problems = [criterion.problem(outcome) for criterion in task.criteria]
    outcome.problems = [problem for problem in problems if problem is not None]
    if result.status == "failed":
        outcome.problems.append(f"run: {result.stop_reason}")
    return outcome


def _provider(recording, is_live):
    """Return the LLM of a task; a live run writes the recording anew."""
    if not is_live:
        return FakeLLM.from_recording(recording)
    recording.unlink(missing_ok=True)
    return Recorder(OpenRouter(), recording)


def run_agent(agent_name, root=ROOT, is_live=False):
    """Run every task of one agent and return the outcomes, by file name."""
    outcomes = []
    for path in sorted((root / "tasks" / agent_name).glob("*.yaml")):
        recording = root / "recordings" / agent_name / f"{path.stem}.jsonl"
        llm = _provider(recording, is_live)
        outcomes.append(run_task(path.stem, load_task(path), agent_name, llm))
    return outcomes


def _row(outcome):
    """Return the table row of one task."""
    usage = outcome.usage
    tokens = usage.input_tokens + usage.output_tokens
    result = "pass" if outcome.passed else "fail"
    return (
        f"| {outcome.name} | {result} | {outcome.steps} | {len(outcome.tools)} | {tokens} "
        f"| {usage.cost:.4f} | {outcome.time:.2f} |"
    )


def summary(agent_name, outcomes):
    """Return the report per task and in total, as Markdown."""
    passed = sum(outcome.passed for outcome in outcomes)
    usage = sum((outcome.usage for outcome in outcomes), Usage())
    tokens = usage.input_tokens + usage.output_tokens
    lines = [
        f"# Evals of {agent_name}",
        "",
        "| Task | Result | Steps | Tool calls | Tokens | Cost | Time (s) |",
        "|---|---|---|---|---|---|---|",
        *(_row(outcome) for outcome in outcomes),
        "",
        f"Total: {passed} of {len(outcomes)} passed, "
        f"{sum(outcome.steps for outcome in outcomes)} steps, "
        f"{sum(len(outcome.tools) for outcome in outcomes)} tool calls, {tokens} tokens, "
        f"cost {usage.cost:.4f}, {sum(outcome.time for outcome in outcomes):.2f} s.",
    ]
    failures = [
        f"- {outcome.name}: {problem}" for outcome in outcomes for problem in outcome.problems
    ]
    return "\n".join([*lines, *(["", "Failures:", *failures] if failures else [])]) + "\n"


def main(argv=None, root=ROOT):
    """Run one agent's tasks, write ``reports/summary.md`` and return the exit code."""
    parser = argparse.ArgumentParser(prog="evals.run", description=__doc__)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.live and not os.environ.get("OPENROUTER_API_KEY"):
        print("evals: --live needs OPENROUTER_API_KEY in the environment", file=sys.stderr)
        return 2
    try:
        if args.agent not in SUITES:
            gd.agents.named(args.agent)
        outcomes = run_agent(args.agent, root, args.live)
    except gd.errors.GeomindError as error:
        print(f"evals: {error}", file=sys.stderr)
        return 2
    if not outcomes:
        print(f"evals: no tasks in {root / 'tasks' / args.agent}", file=sys.stderr)
        return 2
    text = summary(args.agent, outcomes)
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / "summary.md").write_text(text)
    print(text)
    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())

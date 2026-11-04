"""Run the tasks of one agent and report: ``python -m evals.run --agent analysis_lead [--live]``.

Offline by default, from ``recordings/``. ``--live`` calls OpenRouter and writes the recording.
Criteria are checked by code, never by an LLM. A suite of ``SUITES`` (``challenge2``) runs its
tasks through a loop instead of one agent. ``--report`` runs every task through the three loops
(``ToolLoop``, ``DesignLoop``, ``CompareLoop``) and writes ``reports/summary.md``.
"""

import argparse
import multiprocessing
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

import geomind as gd
from evals.tasks_format import VerifiedCriterion, load_task
from geomind import runtime
from geomind.agents import Route
from geomind.context import ProblemState
from geomind.engine import Context
from geomind.engine.engine import STEP_OPTIONS
from geomind.engine.hooks import CostBudget
from geomind.providers import FakeLLM, OpenRouter, Recorder
from geomind.run import loop_of
from geomind.stores import FileWorkspace, MemoryRunStore
from geomind.stores.knowledge import FolderKnowledge
from geomind.tools.base import RENAMED_TOOLS
from geomind.types import ToolCall, Usage
from geomind.utils.models import fetch_prices

ROOT = Path(__file__).parent
CHAT = "eval"
SUITES = {"challenge2": "design", "compare": "study_compare", "alternatives": "compare"}
"""Task folders run through a loop rather than one agent: the folder name and its loop."""
SUITE_AGENT = "design_lead"
"""The agent that runs a suite's task alone, through the ``ToolLoop``."""
REPORT_LOOPS = {"tool": "ToolLoop", "design": "DesignLoop", "compare": "CompareLoop"}
LOOP_SUITES = ("design", "study_compare", "compare")
"""The loops of the report: the name in ``LOOPS`` and the class.

NOTE: ``compare`` is the loop of 0.4.6; the ``compare`` suite's own recording was made on
``StudyCompareLoop``, which its own runs (``--agent compare``) use.
"""


@dataclass
class Outcome:
    """What one task did, and what the criteria found."""

    name: str
    answer: str = ""
    tools: list = field(default_factory=list)
    succeeded: list = field(default_factory=list)
    """The tools, in order, whose result was not an error."""
    questions: list = field(default_factory=list)
    state: dict = field(default_factory=dict)
    steps: int = 0
    criteria: int = 0
    usage: Usage = Usage()
    time: float = 0.0
    problems: list = field(default_factory=list)
    verdict: dict = field(default_factory=dict)
    unanswered: list = field(default_factory=list)
    read: str = ""
    partial: bool = False
    """The answer is the one the engine wrote from the record because a limit stopped the run."""

    @property
    def met(self):
        """Return how many criteria held."""
        return max(self.criteria - len(self.problems), 0)

    @property
    def passed(self):
        """Tell whether every criterion held."""
        return not self.problems


STATE_HEADING = "Problem state, version "
CASE_LINE = "Case: "


def _read(events):
    """Return the text of every message the agent was sent and did not write itself.

    The problem state is left out, as the agent writes its notes and questions there, but for its
    ``Case:`` line: the case's span and parts, which tools set from the files and the user.
    """
    seen = {
        (message.role, message.content)
        for event in events
        if event.type == "llm.completed"
        for message in event.messages
        if message.role != "assistant" and not message.content.startswith(STATE_HEADING)
    }
    cases = {
        line
        for event in events
        if event.type == "llm.completed"
        for message in event.messages
        if message.content.startswith(STATE_HEADING)
        for line in message.content.splitlines()
        if line.startswith(CASE_LINE)
    }
    return "\n".join([*(content for _, content in sorted(seen)), *sorted(cases)])


def _workspace(task):
    """Return the workspace and the project of a task."""
    if task.plant is None:
        return None, None
    folder = Path(task.plant)
    folder_of = runtime.get("knowledge_dir")
    knowledge = FolderKnowledge(folder_of) if folder_of else None
    return FileWorkspace(folder.parent, knowledge=knowledge), folder.name


def is_step_limit(request):
    """Tell whether a request is the question a run asks at its step limit."""
    options = [option.value for option in request.options or ()]
    return options == list(STEP_OPTIONS)


LIMIT_STOPS = ("step_limit", "denied")
"""The stop reasons whose answer, when there is one, the engine wrote from the run's record."""

UNKNOWN = "unknown"
"""A rule-answered task's reply to a question no rule covers: the user does not know."""
UNSET = re.compile(r"unset|unknown|leave|keep|skip", re.IGNORECASE)
"""The options a question no rule covers is answered with: one that leaves the value open."""


def ruled_answer(request, rules, unanswered):
    """Return the reply a task's rules give to ``request``, and note one no rule covers."""
    values = [option.value for option in request.options or ()]
    for rule in rules:
        fits = rule.answer in values if values else not rule.only_options
        if fits and re.search(rule.match, request.message, re.IGNORECASE):
            return rule.answer
    unanswered.append(request.message)
    if values:
        return next((value for value in values if UNSET.search(value)), values[-1])
    return UNKNOWN


def _drive(run, answers, unanswered=None):
    """Start the run and reply to its questions; a question with no reply left ends it.

    A task's ``max_steps`` is its limit: the question at the step limit is answered ``stop``.
    Plain replies go to the other questions in order; with rules (``AnswerRule``), every
    question is answered by the first rule that matches it, else as the user who does not
    know, and noted in ``unanswered``.
    """
    rules = [item for item in answers if not isinstance(item, str)]
    replies = [item for item in answers if isinstance(item, str)]
    unanswered = [] if unanswered is None else unanswered
    result = run.start()
    for _ in range(MAX_ANSWERS):
        if result.status != "waiting":
            break
        if is_step_limit(result.request):
            reply = "stop"
        elif rules:
            reply = ruled_answer(result.request, rules, unanswered)
        elif replies:
            reply = replies.pop(0)
        else:
            break
        result = run.resume(result.request.id, {"text": reply})
    return result


MAX_ANSWERS = 12
"""The most questions one task answers, so a run that keeps asking ends."""


class StoredArtifacts:
    """The artifacts of one chat, read as a session of that chat reads them."""

    def __init__(self, store, chat_id):
        """Keep the store and the chat."""
        self.store = store
        self.chat_id = chat_id

    def load_artifact(self, key):
        """Return an artifact of the chat, or ``None``."""
        return self.store.load_chat_artifact(self.chat_id, key)


def verdict(store, chat_id, state):
    """Return gemini's checks on the final state's design and result, as ``verify_design``."""
    from geomind.verify.design import verify_design

    context = Context(
        problem=ProblemState.model_validate(state), session=StoredArtifacts(store, chat_id)
    )
    return verify_design(context)


def new_run(task, agent_name, llm, store, loop=None, hooks=()):
    """Return the run of a task: its own agent or suite loop, or the loop ``loop`` names."""
    workspace, project = _workspace(task)
    loop = loop or SUITES.get(agent_name)
    agent_name = SUITE_AGENT if loop == "tool" and agent_name in SUITES else agent_name
    run = gd.Run(
        task.message,
        chat=CHAT,
        project=project,
        history=task.history,
        llm=llm,
        store=store,
        workspace=workspace,
        permissions=gd.Permissions(mode="auto"),
        hooks=hooks,
        agent=None if loop in LOOP_SUITES else gd.agents.named(agent_name),
    )
    if loop == "study_compare":
        run.loop = gd.loops.StudyCompareLoop(gd.agents.DesignLead(), gd.agents.Reviewer())
    if loop in ("design", "compare"):
        run.loop = loop_of(Route(kind="loop", loop=loop))
    return run


class SetupAgent(gd.Agent):
    """Make a task's setup calls by rule, one per step, then finish: no model is called."""

    def __init__(self, calls):
        """Declare the tools the calls name and a rule model."""
        super().__init__()
        for name in dict.fromkeys(call.tool for call in calls):
            tool = getattr(gd.tools.gemini, name, None) or getattr(gd.tools, name)
            setattr(self, name, tool)
        self.model = gd.Model(name="rule")
        self._calls = calls

    async def forward(self, context):
        """Return the next setup call, or the end once each has run."""
        done = sum(message.role == "tool" for message in context.messages)
        if done == len(self._calls):
            return gd.Action(text="set up")
        call = self._calls[done]
        return gd.Action(
            text="", tool_calls=(ToolCall(id=f"setup-{done}", name=call.tool, input=call.input),)
        )


def set_up(task, store):
    """Run a task's setup calls in its chat, so its agent starts from their state and artifacts."""
    if not task.setup:
        return
    workspace, project = _workspace(task)
    result = gd.Run(
        "set up",
        chat=CHAT,
        project=project,
        llm=FakeLLM([]),
        store=store,
        workspace=workspace,
        permissions=gd.Permissions(mode="auto"),
        agent=SetupAgent(task.setup),
    ).start()
    failed = [
        event.output
        for event in store.load_events(result.run_id)
        if event.type == "tool.result" and event.is_error
    ]
    if result.status != "done" or failed:
        raise gd.errors.GeomindError(f"evals: setup failed: {failed or result.message}")


def run_task(name, task, agent_name, llm, loop=None, hooks=()):
    """Run one task, through ``loop`` if given, and return its outcome."""
    store = MemoryRunStore()
    set_up(task, store)
    run = new_run(task, agent_name, llm, store, loop, hooks)
    started = perf_counter()
    unanswered = []
    with runtime.settings(**({"max_steps": task.max_steps} if task.max_steps else {})):
        result = _drive(run, task.answers, unanswered)
    events = store.load_events(result.run_id)
    outcome = Outcome(
        name=name,
        answer=str(result.answer or ""),
        tools=[
            RENAMED_TOOLS.get(e.tool, e.tool)
            for e in events
            if e.type == "tool.result" and e.call_id
        ],
        succeeded=[
            RENAMED_TOOLS.get(e.tool, e.tool)
            for e in events
            if e.type == "tool.result" and e.call_id and not e.is_error
        ],
        questions=[e.request.message for e in events if e.type == "request"],
        state=store.load_state(CHAT) or {},
        steps=result.steps,
        criteria=len(task.criteria),
        usage=result.usage,
        time=perf_counter() - started,
        unanswered=unanswered,
        read=_read(events),
        partial=result.stop_reason in LIMIT_STOPS and bool(result.answer),
    )
    if any(isinstance(criterion, VerifiedCriterion) for criterion in task.criteria):
        outcome.verdict = verdict(store, CHAT, outcome.state)
    problems = [criterion.problem(outcome) for criterion in task.criteria]
    outcome.problems = [problem for problem in problems if problem is not None]
    problem = run_problem(task, result)
    if problem is not None:
        outcome.problems.append(problem)
    return outcome


def run_problem(task, result):
    """Return why the run itself fails its task, or ``None``.

    A task's ``max_steps`` is a limit the task means to reach: its run ends ``step_limit`` when
    the question at the limit is answered ``stop``, and that end is the one the task checks.
    """
    if result.status != "failed":
        return None
    if task.max_steps is not None and result.stop_reason == "step_limit":
        return None
    return f"run: {result.stop_reason}"


def _provider(recording, is_live):
    """Return the LLM of a task; a live run writes the recording anew."""
    if not is_live:
        return FakeLLM.from_recording(recording)
    recording.unlink(missing_ok=True)
    return Recorder(OpenRouter(), recording)


def run_agent(agent_name, root=ROOT, is_live=False, loop=None, only=None, max_cost=None):
    """Run every task of one agent, or the one ``only`` names, through ``loop`` if given.

    A live run caps each task at ``max_cost`` USD, required, with OpenRouter's prices.
    """
    hooks = live_caps(max_cost) if is_live else ()
    outcomes = []
    for path in sorted((root / "tasks" / agent_name).glob(f"{only or '*'}.yaml")):
        recording = root / "recordings" / agent_name / f"{path.stem}.jsonl"
        recording.parent.mkdir(parents=True, exist_ok=True)
        llm = _provider(recording, is_live)
        task = load_task(path)
        outcomes.append(run_task(path.stem, task, agent_name, llm, loop, hooks))
    return outcomes


def live_caps(max_cost):
    """Return the cost cap of one live task; a live run without one is refused."""
    if max_cost is None:
        raise gd.errors.RunError("evals: --live needs --max-cost USD, the cap of each task")
    return (CostBudget(max_cost, prices=fetch_prices()),)


def _cell(root, agent_name, loop, only=None):
    """Return the outcomes of a task folder, or one task, through a loop; a break fails it."""
    try:
        return run_agent(agent_name, root, loop=loop, only=only)
    except Exception as error:
        name = only or agent_name
        return [Outcome(name=f"{name} ({type(error).__name__}: {error})", problems=["run"])]


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


def _loop_row(outcome):
    """Return the table row of one task through one loop: criteria met, then the costs."""
    usage = outcome.usage
    tokens = usage.input_tokens + usage.output_tokens
    return (
        f"| {outcome.name} | {outcome.met} of {outcome.criteria} | {outcome.steps} "
        f"| {len(outcome.tools)} | {tokens} | {usage.cost:.4f} | {outcome.time:.2f} |"
    )


def _loop_table(title, outcomes):
    """Return the table of one loop: a row per task and the total."""
    usage = sum((outcome.usage for outcome in outcomes), Usage())
    total = (
        f"| Total | {sum(outcome.met for outcome in outcomes)} of "
        f"{sum(outcome.criteria for outcome in outcomes)} "
        f"| {sum(outcome.steps for outcome in outcomes)} "
        f"| {sum(len(outcome.tools) for outcome in outcomes)} "
        f"| {usage.input_tokens + usage.output_tokens} | {usage.cost:.4f} "
        f"| {sum(outcome.time for outcome in outcomes):.2f} |"
    )
    return [
        f"## {title}",
        "",
        "| Task | Criteria met | Steps | Tool calls | Tokens | Cost | Time (s) |",
        "|---|---|---|---|---|---|---|",
        *(_loop_row(outcome) for outcome in outcomes),
        total,
        "",
    ]


def report(root=ROOT, workers=None):
    """Return the report of every task through each loop, as Markdown.

    ``workers`` runs the cells (one task through one loop) in that many processes, each on its
    own recording and store, so the table is the same; unset, one after another.

    Every task runs from its own recording through ``ToolLoop`` (the task's agent, or the DesignLead
    alone for a suite), ``DesignLoop`` and ``CompareLoop``. The recording is the decisions of one
    loop, so a loop whose agents ask for different steps meets a task it cannot finish: its
    criteria are unmet, which is what the table shows.
    """
    folders = sorted(path.name for path in (root / "tasks").iterdir() if path.is_dir())
    lines = [
        "# Evals: ToolLoop, DesignLoop and CompareLoop",
        "",
        "Offline, from the recordings of `evals/recordings/`; generated by "
        "`python -m evals.run --report`. Time varies from run to run.",
        "",
    ]
    cells = [
        (root, folder, loop, path.stem)
        for loop in REPORT_LOOPS
        for folder in folders
        for path in sorted((root / "tasks" / folder).glob("*.yaml"))
    ]
    found = dict(zip(cells, _cells(cells, workers)))
    for loop, title in REPORT_LOOPS.items():
        outcomes = []
        for cell, cell_outcomes in found.items():
            if cell[2] == loop:
                outcomes += [_renamed(outcome, cell[1]) for outcome in cell_outcomes]
        lines += _loop_table(title, outcomes)
    return "\n".join(lines) + "\n"


def _cells(cells, workers):
    """Return the outcomes of each cell, in order, in ``workers`` processes when given.

    NOTE: a process runs one cell and exits, so the memory of a heavy cell is given back before
    the next one starts.
    """
    if not workers or workers < 2:
        return [_cell(*cell) for cell in cells]
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=workers, mp_context=context, max_tasks_per_child=1
    ) as pool:
        return list(pool.map(_cell, *zip(*cells)))


def _renamed(outcome, folder):
    """Return the outcome named by its folder and task."""
    outcome.name = f"{folder}/{outcome.name}"
    return outcome


def main(argv=None, root=ROOT):
    """Run one agent's tasks or the report, write the Markdown and return the exit code."""
    parser = argparse.ArgumentParser(prog="evals.run", description=__doc__)
    parser.add_argument("--agent")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-cost", type=float, help="with --live, the USD cap of each task")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--workers", type=int, help="processes of the report; unset, one")
    args = parser.parse_args(argv)
    if args.report:
        return _command_report(root, args.workers)
    if not args.agent:
        parser.error("one of --agent or --report is needed")
    if args.live and not os.environ.get("OPENROUTER_API_KEY"):
        print("evals: --live needs OPENROUTER_API_KEY in the environment", file=sys.stderr)
        return 2
    try:
        if args.agent not in SUITES:
            gd.agents.named(args.agent)
        outcomes = run_agent(args.agent, root, args.live, max_cost=args.max_cost)
    except gd.errors.GeomindError as error:
        print(f"evals: {error}", file=sys.stderr)
        return 2
    if not outcomes:
        print(f"evals: no tasks in {root / 'tasks' / args.agent}", file=sys.stderr)
        return 2
    text = summary(args.agent, outcomes)
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / f"{args.agent}.md").write_text(text)
    print(text)
    return 0 if all(outcome.passed for outcome in outcomes) else 1


def _command_report(root, workers=None):
    """Write ``reports/summary.md`` and print it."""
    text = report(root, workers)
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / "summary.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Size, optimise, verify and repeat until a design passes."""

import asyncio
import json

from geomind import tools
from geomind.agents import Designer, Economist, Explainer, Verifier
from geomind.agents.agent import Agent, Model
from geomind.engine.hooks import Verified
from geomind.loops.loop import Loop
from geomind.tools import Delegate
from geomind.tools.files import project_file_names
from geomind.tools.gemini.plants import project_plant_names
from geomind.types import Action, ToolCall
from geomind.verify.design import verify_design

MARK = "design loop: "
DESIGN_TOKENS = 1000
EXPLANATION_TOKENS = 6000
APPROVE = "approve"
RESTORE = "restore"
CASE_OPTIONS = (
    {"value": APPROVE, "label": "Approve the changed case: verify the design on it"},
    {"value": RESTORE, "label": "Restore the case I gave and design for it"},
)
SIDES = (
    ("subsurface", "Subsurface side (wells, reservoir, injection, pressure): change the doublets."),
    ("surface", "Surface side (heating, cooling, equipment, topology): change the surface plant."),
    ("sizing", "Resize, keeping the topology: the plant works, a size does not."),
    ("coupled", "Coupled: change the subsurface first, then the surface."),
)


def repeated(rounds):
    """Tell whether the last round failed exactly as the one before."""
    return len(rounds) >= 2 and sorted(rounds[-1]) == sorted(rounds[-2])


def failure_lines(found, domain):
    """Return one line per failure of a domain: gemini's name for it and what it measured."""
    return [
        f"- {item['name']}: {item['detail']}"
        for item in found["failures"]
        if item["domain"] == domain
    ]


def routed_task(round_number, max_rounds, design, result, found):
    """Return the designer's task for the next round: the failures, routed by their domain."""
    parts = [
        f"Round {round_number} of at most {max_rounds}. The last design {design} ({result}) failed "
        "gemini's checks."
    ]
    for domain, instruction in SIDES:
        lines = failure_lines(found, domain)
        if lines:
            parts.append("\n".join([instruction, *lines]))
    parts.append(
        "Every earlier result of a design you change is stale: size it again under a new name, "
        "simulate the whole year, check it, optimize it, and record the new design.reference and "
        "design.result."
    )
    return "\n\n".join(parts)


def driver_calls(messages):
    """Return ``(name, output)`` of each call the driver made, in order, with the tool's output."""
    outputs = {item.tool_call_id: item.content for item in messages if item.role == "tool"}
    return [
        (call.name, outputs.get(call.id, ""))
        for item in messages
        if item.role == "assistant"
        for call in item.tool_calls
    ]


def notes(messages):
    """Return the driver's notes of earlier rounds, as it wrote them after ``MARK``."""
    return [
        json.loads(item.content.removeprefix(MARK))
        for item in messages
        if item.role == "assistant" and item.content.startswith(MARK)
    ]


def act(note, index, name, **tool_input):
    """Return one action of the driver: its note, and its call number ``index`` of the run."""
    call = ToolCall(id=f"loop-{index}-{name}", name=name, input=tool_input)
    return Action(text=MARK + json.dumps(note), tool_calls=(call,))


class DesignDriver(Agent):
    """Drive one design by rule: the designer optimises, the verifier checks, gemini decides.

    NOTE: every decision is code over the run's own history and store, so a resumed or replayed
    run makes the same moves; the agents it delegates to are the only model calls.
    """

    def __init__(self, designer=None, verifier=None, max_rounds=5):
        """Declare the four delegated agents, the state, the answer and a rule model."""
        super().__init__()

        # Tools
        self.designer = Delegate(designer or Designer(), max_summary_tokens=DESIGN_TOKENS)
        self.verifier = Delegate(verifier or Verifier(), max_summary_tokens=DESIGN_TOKENS)
        self.economist = Delegate(Economist(), max_summary_tokens=DESIGN_TOKENS)
        self.explainer = Delegate(Explainer(), max_summary_tokens=EXPLANATION_TOKENS)
        self.update_state = tools.update_state
        self.accept_case = tools.gemini.accept_case
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(name="rule")
        self._max_rounds = max_rounds

    async def forward(self, context):
        """Decide the next move from the calls made so far."""
        calls = driver_calls(context.messages)
        index = len(calls)
        note = {"round": max(rounds(calls), 1)}
        if not calls:
            return self.begin(context, note, index)
        name, output = calls[-1]
        if name == "designer":
            return self.after_design(context, note, index)
        if name == "ask_user":
            return self.after_question(context, note, index, output)
        if name in ("verifier", "accept_case"):
            return await self.after_verification(context, calls)
        if name == "economist":
            return act(note, index, "explainer", task=explainer_task(context, calls))
        if name == "explainer":
            answer = f"{output}\n\n{MARK}stop: verified after round {note['round']}"
            return act({**note, "stop": "verified"}, index, "finish", answer=answer)
        return act(note, index, "finish", answer=stop_answer(notes(context.messages)[-1]))

    def begin(self, context, note, index):
        """Start with the designer, or ask for a missing case when no project file can hold it."""
        missing = missing_case(context.problem)
        if missing is not None and not project_file_names(context):
            return act(
                {**note, "missing": missing}, index, "ask_user", question=question_of(missing)
            )
        return act(note, index, "designer", task=self.first_task(context))

    def first_task(self, context):
        """Return the designer's first task: the request, the project's plants and the rounds."""
        request = request_of(context)
        return (
            f"{request}{project_plants_text(context)}{project_files_text(context)}\n\n"
            f"Round 1 of at most {self._max_rounds}. "
            "Read the case, then size a plant, simulate the whole year, check it, optimize it, "
            "simulate the optimised design and record design.reference and design.result."
        )

    def after_design(self, context, note, index):
        """Verify the design, or ask the user for the case the design run still lacks."""
        missing = missing_case(context.problem)
        if missing is None:
            return act(note, index, "verifier", task=verifier_task(context))
        if note["round"] >= self._max_rounds:
            answer = (
                f"No design was verified: the problem state has {missing}. {MARK}stop: no_case "
                f"after round {note['round']}."
            )
            return act({**note, "stop": "no_case"}, index, "finish", answer=answer)
        return act({**note, "missing": missing}, index, "ask_user", question=question_of(missing))

    def after_question(self, context, note, index, answer):
        """Act on the user's answer: on a changed case, accept or restore it; else design."""
        asked = notes(context.messages)[-1]
        if not asked.get("case_changed"):
            return act(note, index, "designer", task=answered_task(context, answer))
        if answer.strip() == APPROVE:
            return act({**note, "approved": True}, index, "accept_case")
        return act(note, index, "designer", task=restored_task(context, note["round"] + 1))

    async def after_verification(self, context, calls):
        """Check the design again with gemini, then cost it, route its failures, or stop."""
        found = await asyncio.to_thread(verify_design, context)
        round_number = rounds(calls)
        design = context.problem.design_state.reference
        result = context.problem.verification.get("result")
        index = len(calls)
        changed = case_change(found)
        if changed is not None:
            note = {"round": round_number, "case_changed": True}
            question = changed_question(changed)
            return act(note, index, "ask_user", question=question, options=list(CASE_OPTIONS))
        if found["passed"]:
            task = economist_task(design, result, context.problem)
            return act({"round": round_number, "passed": True}, index, "economist", task=task)
        failed = sorted(item["name"] for item in found["failures"])
        history = [note["failures"] for note in notes(context.messages) if "failures" in note]
        note = {"round": round_number, "design": design, "result": result, "failures": failed}
        if round_number >= self._max_rounds:
            return stop(context, {**note, "stop": "max_rounds"}, index)
        if repeated([*history, failed]):
            return stop(context, {**note, "stop": "repeated_failure"}, index)
        task = routed_task(round_number + 1, self._max_rounds, design, result, found)
        return act(note, index, "designer", task=task)


def request_of(context):
    """Return the run's own request: the last user message, after the chat's earlier turns."""
    return next(item.content for item in reversed(context.messages) if item.role == "user")


def project_plants_text(context):
    """Return the sentence naming the project's plant files, or ``""`` when it has none."""
    names = project_plant_names(context)
    if not names:
        return ""
    return (
        f"\n\nThe project's plants: {', '.join(names)}. Start from one that fits: read_plant "
        "with project_plant, store it with build_plant, and build a new plant only when none "
        "fits, saying why in an assumption."
    )


def project_files_text(context):
    """Return the sentence naming the project's files, or ``""`` when it has none."""
    names = project_file_names(context)
    if not names:
        return ""
    return (
        f"\n\nThe project's files: {', '.join(names)}. Read them first with read_document and "
        "fill the case from them with set_case (files), before you ask the user for anything."
    )


def missing_case(problem):
    """Return what a design run lacks in the state's case: the case, or its demand; else None."""
    case = problem.case
    if case is None:
        return "no case"
    demand = case.get("demand") or {}
    if not (demand.get("heating") or demand.get("cooling")):
        return "no demand"
    return None


def question_of(missing):
    """Return the question to the user for a case that lacks ``missing``."""
    return (
        f"The design needs a case, and the problem state has {missing}. Which heating and cooling "
        "demand should the design meet (a file of the project, or daily values with a unit), and "
        "which constraints (supply and return temperatures, flows, limits)?"
    )


def answered_task(context, answer):
    """Return the designer's task after the user answered the driver's question on the case."""
    request = request_of(context)
    return (
        f"{request}\n\nThe user answered the question on the case: {answer}\n\nPut it into the "
        "case with set_case, then design."
    )


def case_change(found):
    """Return the ``case_changed`` failure of a verdict, or ``None``."""
    return next((item for item in found["failures"] if item["name"] == "case_changed"), None)


def changed_question(failure):
    """Return the question to the user on a case the design run changed."""
    lines = [
        f"- {item['path']}: {item['change']}"
        + (f" from {json.dumps(item.get('given'))} to {json.dumps(item.get('now'))}")
        for item in failure["changes"]
    ]
    return "\n".join(
        [
            "The design run changed the case you gave. A design is verified only on a case you "
            "approve. The changes:",
            *lines,
            "Approve the changed case, or restore yours?",
        ]
    )


def restored_task(context, round_number):
    """Return the designer's task after the user refused a change of the case."""
    return (
        f"{request_of(context)}\n\nRound {round_number}. The user did not approve the changes of "
        "the case. Call set_case(source='origin') to restore the case the user gave, never change "
        "it again, and design for it: size, simulate the whole year, check, optimize, and record "
        "design.reference and design.result."
    )


def rounds(calls):
    """Return the number of the current round: each round starts with a designer call."""
    return sum(name == "designer" for name, _ in calls)


def verifier_task(context):
    """Return the verifier's task: check the result the designer recorded for its design."""
    design = context.problem.design_state
    if design.reference is None or design.result is None:
        return (
            "The designer recorded no design.reference and design.result. Report that no design "
            "can be verified."
        )
    return (
        f"Verify {design.reference}: run check_results once on its result {design.result} "
        "and record the verification."
    )


def economist_task(design, result, problem):
    """Return the economist's task: cost the verified run, and compare it with what was run."""
    typed = problem.design_state
    start = typed.start_result
    others = [item.result for item in typed.alternatives or ()]
    compared = [reference for reference in (start, *others) if reference]
    against = (
        f"compare it with {', '.join(compared)} (the sized start and the alternatives the "
        "designer simulated)"
        if compared
        else "there is no sized start or alternative in the state to compare it with; say so"
    )
    ranked = (
        " The designer's ranking of the families is in design.study: report it beside yours."
        if problem.design.get("study")
        else ""
    )
    return f"Cost the verified design {design} on its result {result}; {against}.{ranked}"


def metric_text(value):
    """Return a metric of the study as text: ``value unit`` for a quantity, else the value."""
    if isinstance(value, dict) and "value" in value:
        return f"{value['value']} {value.get('unit', '')}".strip()
    return str(value)


def study_table(study):
    """Return the designer's study as a Markdown table, one row per design, or ``""``."""
    runs = (study or {}).get("runs") or ()
    if not runs:
        return ""
    names = sorted({name for run in runs for name in run.get("metrics") or ()})
    rows = [
        "| design | feasible | rank | " + " | ".join(names) + " |",
        "|" + " --- |" * (3 + len(names)),
    ]
    for run in runs:
        metrics = run.get("metrics") or {}
        cells = [metric_text(metrics[name]) if name in metrics else "" for name in names]
        ranks = run.get("ranks") or {}
        rank = ranks.get(study.get("objective"), "")
        rows.append(
            f"| {run.get('design', '')} | {run.get('feasible', '')} | {rank} | "
            + " | ".join(cells)
            + " |"
        )
    return "\n".join(rows)


def explainer_task(context, calls):
    """Return the explainer's task: the request, the verified design and the verifier's report.

    A study the designer recorded (``design.study``) is added as a ranked table.
    """
    request = request_of(context)
    design = context.problem.design_state.reference
    report = next((output for name, output in reversed(calls) if name == "verifier"), "")
    task = (
        f"Explain the verified design {design} for this request:\n\n{request}\n\nThe "
        f"verifier's report:\n\n{report}"
    )
    table = study_table(context.problem.design.get("study"))
    return f"{task}\n\nThe designer's ranked study of the families:\n\n{table}" if table else task


def stop(context, note, index):
    """Return the move that ends the loop without a verified design: the design is set aside."""
    design = context.problem.design or {}
    rejected = [*design.get("rejected", []), *([note["design"]] if note["design"] else [])]
    changes = [{"op": "add", "path": "/design/rejected", "value": rejected}]
    if "reference" in design:
        changes.append({"op": "remove", "path": "/design/reference"})
    if "result" in (context.problem.verification or {}):
        changes.append({"op": "remove", "path": "/verification/result"})
    return act(note, index, "update_state", changes=changes)


def stop_answer(note):
    """Return the answer of a loop that ends without a verified design."""
    failed = ", ".join(note["failures"])
    return (
        f"No design passed gemini's checks. {MARK}stop: {note['stop']} after round "
        f"{note['round']}. The last design {note['design']} ({note['result']}) failed {failed}. "
        "It is kept under design.rejected and is not presented as a solution."
    )


class DesignLoop(Loop):
    """Let ``designer`` propose and ``verifier`` check, for at most ``max_rounds`` rounds.

    A rule-based ``DesignDriver`` runs the rounds in one root run: each delegated agent is a nested
    run in the same log. The ``Designer`` sizes, simulates, checks and optimises; the ``Verifier``
    checks its final design once; only a failure sends it back. A design that passes is costed by
    the ``Economist`` and explained by the ``Explainer``. The loop stops when gemini's checks pass,
    at ``max_rounds``, when one round fails exactly as the one before, or when an agent asks the
    user; a token or cost budget is a hook of the run. Each stop is written in the driver's step
    text and in the answer as ``stop: <reason>``.
    A design run needs a case with a demand in the problem state: when it has none the driver asks
    the user before designing and hands the answer to the designer, and stops with ``no_case`` at
    ``max_rounds`` when the designer still leaves none.
    """

    name = "design"
    driver = DesignDriver

    def __init__(self, designer, verifier, max_rounds=5):
        """Keep the two agents and the limit; a run starts with the designer."""
        self.designer = designer
        self.verifier = verifier
        self.max_rounds = max_rounds
        self.agent = self.driver(designer, verifier, max_rounds)

    def guard(self, engine):
        """Register the ``Verified`` hook once, so no design reaches the user unverified."""
        if not any(isinstance(hook, Verified) for hook in engine.hooks()):
            engine.register_hook(Verified())

    async def run(self, engine, task):
        """Drive the rounds from the context ``task``."""
        self.guard(engine)
        return await engine.run(self.agent, task, loop=self)

    async def resume(self, engine, run_id, request_id=None, answer=None):
        """Continue the rounds where the log left them."""
        self.guard(engine)
        return await engine.resume(run_id, request_id, answer, agent=self.agent, loop=self)

    def state_dict(self):
        """Return the limit of this loop; its position is the run's own history."""
        return {"max_rounds": self.max_rounds}

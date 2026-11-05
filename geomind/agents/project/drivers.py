"""The rule-driven design: the design lead optimises, the reviewer checks, gemini decides.

The ``DesignLoop`` runs it alone; the project lead's comparison runs its subclass.
"""

import json

from geomind import runtime, tools
from geomind.agents.agent import Agent, Model
from geomind.agents.analysis.economist import Economist
from geomind.agents.case.lead import CaseLead
from geomind.agents.design.lead import DesignLead
from geomind.agents.project.explainer import Explainer
from geomind.agents.project.reviewer import Reviewer
from geomind.tools import Delegate
from geomind.tools.files import project_file_names
from geomind.tools.gemini.plants import project_plant_names
from geomind.tools.memory import keep_design
from geomind.types import Action, ToolCall
from geomind.verify.design import verify_design

MARK = "design loop: "
DESIGN_TOKENS = 1000
EXPLANATION_TOKENS = 6000
CASE_CHANGE = "case change needed:"
"""How a design lead's answer names a change of the case, one per line, for the case lead."""
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
    """Return the design lead's task for the next round: the failures, routed by their domain."""
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
    """Drive one design by rule: the design lead optimises, the reviewer checks, gemini decides.

    NOTE: every decision is code over the run's own history and store, so a resumed or replayed
    run makes the same moves; the agents it delegates to are the only model calls.
    """

    def __init__(self, design_lead=None, reviewer=None, max_rounds=5):
        """Declare the four delegated agents, the state, the answer and a rule model."""
        super().__init__()

        # Tools
        self.case_lead = Delegate(CaseLead(), max_summary_tokens=DESIGN_TOKENS)
        self.design_lead = Delegate(design_lead or DesignLead(), max_summary_tokens=DESIGN_TOKENS)
        self.reviewer = Delegate(reviewer or Reviewer(), max_summary_tokens=DESIGN_TOKENS)
        self.economist = Delegate(Economist(), max_summary_tokens=DESIGN_TOKENS)
        self.explainer = Delegate(Explainer(), max_summary_tokens=EXPLANATION_TOKENS)
        self.update_state = tools.update_state
        self.accept_case = tools.gemini.accept_case
        self.set_case = tools.gemini.set_case
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(name="rule")
        self._max_rounds = max_rounds

    def load_loop_state(self, state):
        """Take the logged limit, so a replay or a resume decides as the run did."""
        self._max_rounds = state.get("max_rounds", self._max_rounds)

    async def forward(self, context):
        """Decide the next move from the calls made so far."""
        calls = driver_calls(context.messages)
        index = len(calls)
        note = {"round": max(rounds(calls), 1)}
        if not calls:
            return self.begin(context, note, index)
        name, output = calls[-1]
        if name == "set_case":
            return self.after_loading(context, note, index)
        if name == "case_lead":
            return self.after_formulation(context, note, index, calls)
        if name == "design_lead":
            return self.after_design(context, note, index, output, calls)
        if name == "ask_user":
            return self.after_question(context, note, index, output)
        if name in ("reviewer", "accept_case"):
            return await self.after_verification(context, calls)
        if name == "economist":
            return act(note, index, "explainer", task=explainer_task(context, calls))
        if name == "explainer":
            answer = f"{output}\n\n{MARK}stop: verified after round {note['round']}"
            return act({**note, "stop": "verified"}, index, "finish", answer=answer)
        return act(note, index, "finish", answer=stop_answer(notes(context.messages)[-1]))

    def begin(self, context, note, index):
        """Set a missing case first: the project's case file by rule, else the case lead.

        The case lead works from the chat and any files.
        """
        missing = missing_case(context.problem)
        if missing is None:
            return act(note, index, "design_lead", task=self.first_task(context))
        if has_project_case(context):
            return act(note, index, "set_case", source="project")
        return act(note, index, "case_lead", task=formulation_task(context))

    def after_loading(self, context, note, index):
        """After the project's case is loaded, design; else the case lead completes the case."""
        if missing_case(context.problem) is None:
            return act(note, index, "design_lead", task=self.first_task(context))
        return act(note, index, "case_lead", task=formulation_task(context))

    def after_formulation(self, context, note, index, calls):
        """Design once the case is set; ask the user once for a case still missing, then stop."""
        missing = missing_case(context.problem)
        asked = any("missing" in item for item in notes(context.messages))
        if missing is not None and not asked:
            return act(
                {**note, "missing": missing}, index, "ask_user", question=question_of(missing)
            )
        if missing is not None:
            answer = f"No design was verified: the problem state has {missing}. {MARK}stop: no_case"
            return act({**note, "stop": "no_case"}, index, "finish", answer=answer)
        if rounds(calls) == 0:
            return act(note, index, "design_lead", task=self.first_task(context))
        if any(item.get("restore") for item in notes(context.messages)):
            return act(note, index, "design_lead", task=restored_task(context, note["round"] + 1))
        task = f"Round {note['round'] + 1} of at most {self._max_rounds}.{handover_text(context)}"
        return act(
            note, index, "design_lead", task=f"{task}\n\nThe case was changed: design for it."
        )

    def first_task(self, context):
        """Return the design lead's first task: the request, the project's plants and the rounds."""
        request = request_of(context)
        return (
            f"{request}{project_plants_text(context)}\n\n"
            f"Round 1 of at most {self._max_rounds}. "
            "Read the case, then size a plant, simulate the whole year, check it, optimize it, "
            "simulate the optimised design and record design.reference and design.result."
        )

    def after_design(self, context, note, index, output, calls):
        """Verify the design, or send a missing case or a change the design lead names onward.

        The case lead takes either while rounds are left.
        """
        missing = missing_case(context.problem)
        changes = case_changes_named(output)
        if missing is None and not changes:
            return act(note, index, "reviewer", task=verifier_task(context))
        if missing is None and note["round"] >= self._max_rounds:
            return act(note, index, "reviewer", task=verifier_task(context))
        if note["round"] >= self._max_rounds:
            answer = (
                f"No design was verified: the problem state has {missing}. {MARK}stop: no_case "
                f"after round {note['round']}."
            )
            return act({**note, "stop": "no_case"}, index, "finish", answer=answer)
        return act(note, index, "case_lead", task=change_task(context, missing, changes))

    def after_question(self, context, note, index, answer):
        """Act on the user's answer: on a changed case, accept or restore it; else set the case."""
        asked = notes(context.messages)[-1]
        if not asked.get("case_changed"):
            return act(note, index, "case_lead", task=answered_task(context, answer))
        if answer.strip() == APPROVE:
            return act({**note, "approved": True}, index, "accept_case")
        return act({**note, "restore": True}, index, "case_lead", task=restore_task(context))

    async def after_verification(self, context, calls):
        """Check the design again with gemini, then cost it, route its failures, or stop."""
        found = await runtime.in_gemini_thread(verify_design, context)
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
            await runtime.in_gemini_thread(remember_design, context, found)
            task = economist_task(design, result, context.problem)
            return act({"round": round_number, "passed": True}, index, "economist", task=task)
        failed = sorted(item["name"] for item in found["failures"])
        history = [note["failures"] for note in notes(context.messages) if "failures" in note]
        note = {"round": round_number, "design": design, "result": result, "failures": failed}
        if round_number >= self._max_rounds:
            return stop(context, {**note, "stop": "max_rounds"}, index)
        if should_stop_repeated([*history, failed], design):
            return stop(context, {**note, "stop": "repeated_failure"}, index)
        stuck = stuck_requirements([*history, failed])
        if design is not None and stuck:
            return stop(context, {**note, "stop": "requirement_budget", "stuck": stuck}, index)
        task = routed_task_of(context, round_number + 1, self._max_rounds, design, result, found)
        return act(note, index, "design_lead", task=task)


def remember_design(context, found):
    """Keep a design that passed as experience, with the lessons of the rejected rounds."""
    rejected = [note["failures"] for note in notes(context.messages) if "failures" in note]
    keep_design(context, found, rejected)


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
        f"\n\nThe project's files: {', '.join(names)}. Read them with read_rag and set the "
        "case from them with set_case (files), before you ask the user for anything."
    )


def has_project_case(context):
    """Tell whether the run's project holds a case file the case lead can load."""
    workspace = context.session.workspace
    if workspace is None or context.project is None or not hasattr(workspace, "case"):
        return False
    return workspace.case(context.project) is not None


def formulation_task(context):
    """Return the case lead's task: the request, the project's case file and its files."""
    own = (
        "\n\nThe project holds a case file: start from set_case(source='project'), then add what "
        "it lacks."
        if has_project_case(context)
        else ""
    )
    return (
        f"{request_of(context)}{own}{project_files_text(context)}\n\nSet the case for this design."
    )


def case_changes_named(output):
    """Return the lines of a design lead's answer that name a change of the case."""
    return [line.strip() for line in str(output).splitlines() if CASE_CHANGE in line]


def change_task(context, missing, changes):
    """Return the case lead's task when a round found the case missing or naming a change."""
    lines = [f"The problem state has {missing}." if missing else "", *changes]
    shown = "\n".join(line for line in lines if line)
    return (
        f"{request_of(context)}{project_files_text(context)}\n\nThe last design round needs the "
        f"case changed:\n{shown}\n\nChange the case with the files' values, or record an "
        "assumption, or ask the user; never change a value a file states."
    )


def restore_task(context):
    """Return the case lead's task after the user refused a change of the case."""
    return (
        f"{request_of(context)}\n\nThe user did not approve the changes of the case. Call "
        "set_case(source='origin') to restore the case the user gave."
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
    """Return the design lead's task after the user answered the driver's question on the case.

    The last round's answer goes with it, at most ``HANDOVER_CHARACTERS``: what it read, set and
    failed on, so the new round goes on from there instead of reading everything again.
    """
    request = request_of(context)
    return (
        f"{request}{project_files_text(context)}\n\nThe user answered the question on the case: "
        f"{answer}{handover_text(context)}\n\nPut it into the case with set_case."
    )


def handover_text(context, agent="design_lead"):
    """Return the last answer of ``agent`` for the next task, or ``""`` before it ran."""
    designed = [output for name, output in driver_calls(context.messages) if name == agent]
    if not designed:
        return ""
    return f"\n\nThe last round handed over:\n{designed[-1][:HANDOVER_CHARACTERS]}"


def routed_task_of(context, round_number, max_rounds, design, result, found):
    """Return ``routed_task`` with the last round's handover, so the round goes on from there."""
    task = routed_task(round_number, max_rounds, design, result, found)
    return f"{task}{handover_text(context)}"


def should_stop_repeated(history, design):
    """Tell whether the loop stops for a repeated failure: a design failed as the one before.

    A round that recorded no design (its steps ran out) is no failure of a design, so the loop
    goes on to its round limit.
    """
    return design is not None and repeated(history)


REQUIREMENT_ROUNDS = 3
"""Rounds in a row one requirement may fail before the loop stops and reports it (IMP-016)."""


def stuck_requirements(history):
    """Return the requirements that failed in each of the last ``REQUIREMENT_ROUNDS`` rounds.

    QA-090: 18 variants over 2 h 40 chased one rule while the rest changed. A rule that fails
    round after round, whatever else changes, goes back to the user with what was tried.
    """
    if len(history) < REQUIREMENT_ROUNDS:
        return []
    last = [set(item) for item in history[-REQUIREMENT_ROUNDS:]]
    return sorted(set.intersection(*last))


HANDOVER_CHARACTERS = 6000
"""The most characters of the last round's answer that the next round's task carries."""


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
    """Return the design lead's task after the user refused a change of the case."""
    return (
        f"{request_of(context)}\n\nRound {round_number}. The user did not approve the changes of "
        "the case, so the case the user gave is restored. Never ask to change it again, and design "
        "for it: size, simulate the whole year, check, optimize, and record design.reference and "
        "design.result."
    )


def rounds(calls):
    """Return the number of the current round: each round starts with a design lead call."""
    return sum(name == "design_lead" for name, _ in calls)


def verifier_task(context):
    """Return the reviewer's task: check the result the design lead recorded for its design."""
    design = context.problem.design_state
    if design.reference is None or design.result is None:
        return (
            "The design lead recorded no design.reference and design.result. Report that no design "
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
        "design_lead simulated)"
        if compared
        else "there is no sized start or alternative in the state to compare it with; say so"
    )
    ranked = (
        " The design lead's ranking of the families is in design.study: report it beside yours."
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
    """Return the design lead's study as a Markdown table, one row per design, or ``""``."""
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
    """Return the explainer's task: the request, the verified design and the reviewer's report.

    A study the design lead recorded (``design.study``) is added as a ranked table.
    """
    request = request_of(context)
    design = context.problem.design_state.reference
    report = next((output for name, output in reversed(calls) if name == "reviewer"), "")
    task = (
        f"Explain the verified design {design} for this request:\n\n{request}\n\nThe "
        f"reviewer's report:\n\n{report}"
    )
    table = study_table(context.problem.design.get("study"))
    return (
        f"{task}\n\nThe design_lead's ranked study of the families:\n\n{table}" if table else task
    )


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
        + (
            f" {', '.join(note['stuck'])} failed in each of the last {REQUIREMENT_ROUNDS} rounds: "
            "the user decides whether to accept the design with it open, change the requirement, "
            "or stop."
            if note.get("stuck")
            else ""
        )
    )

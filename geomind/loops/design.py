"""Propose, simulate, verify and repeat until a design passes."""

import asyncio
import json

from geomind import tools
from geomind.agents import Designer, Economist, Explainer, Verifier
from geomind.agents.agent import Agent, Model
from geomind.engine.hooks import Verified
from geomind.loops.loop import Loop
from geomind.tools import Delegate
from geomind.types import Action, ToolCall
from geomind.verify.design import verify_design

MARK = "design loop: "
SET_BRIEF = (
    "First set the brief of the problem state with set_brief: the preset hackathon_2027 when the "
    "request is the GEMINI hackathon challenge, otherwise the values the request gives. Never "
    "take the hackathon's numbers for another brief; ask the user for a demand it does not give."
)
DESIGN_TOKENS = 1000
EXPLANATION_TOKENS = 6000
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
    """Return one line per failed check of a domain: its name, value and limit."""
    checks = {check["name"]: check for check in found.get("checks", [])}
    lines = []
    for item in found["failures"]:
        if item["domain"] != domain:
            continue
        check = checks.get(item["name"])
        if check is None:
            lines.append(f"- {item['name']}: {found.get('reason', 'no check')}")
            continue
        value, limit = check["value"], check["limit"]
        lines.append(
            f"- {item['name']}: {value.get('value')} {value.get('unit', '')} against "
            f"{limit.get('value')} {limit.get('unit', '')}"
        )
    return lines


def routed_brief(round_number, max_rounds, design, result, found):
    """Return the designer's brief for the next round: the failures, routed by their domain."""
    parts = [
        f"Round {round_number} of at most {max_rounds}. The last design {design} ({result}) failed "
        "gemini's checks."
    ]
    for domain, instruction in SIDES:
        lines = failure_lines(found, domain)
        if lines:
            parts.append("\n".join([instruction, *lines]))
    parts.append(
        "Every earlier result of a design you change is stale: build it under a new name, simulate "
        "the whole year again and check it. Record the new design.reference."
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
    """Drive one design by rule: the designer proposes, the verifier checks, gemini's checks decide.

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
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(name="rule")
        self._max_rounds = max_rounds

    async def forward(self, context):
        """Decide the next move from the calls made so far."""
        calls = driver_calls(context.messages)
        index = len(calls)
        if not calls:
            return act({"round": 1}, index, "designer", task=self.first_brief(context))
        name, output = calls[-1]
        note = {"round": rounds(calls)}
        if name == "designer":
            return self.after_design(context, note, index)
        if name == "ask_user":
            return act(note, index, "designer", task=answered_task(context, output))
        if name == "verifier":
            return await self.after_verification(context, calls)
        if name == "economist":
            return act(note, index, "explainer", task=explainer_task(context))
        if name == "explainer":
            answer = f"{output}\n\n{MARK}stop: verified after round {note['round']}"
            return act({**note, "stop": "verified"}, index, "finish", answer=answer)
        return act(note, index, "finish", answer=stop_answer(notes(context.messages)[-1]))

    def first_brief(self, context):
        """Return the designer's first brief: the user's request and the rules of the rounds."""
        request = next(item.content for item in context.messages if item.role == "user")
        return (
            f"{request}\n\nRound 1 of at most {self._max_rounds}. {SET_BRIEF} Then propose the "
            "design families, build one design, simulate the whole year, check it and record "
            "design.reference."
        )

    def after_design(self, context, note, index):
        """Verify the design, or ask the user for the brief the design run still lacks."""
        missing = missing_brief(context.problem)
        if missing is None:
            return act(note, index, "verifier", task=verifier_task(context))
        if note["round"] >= self._max_rounds:
            answer = (
                f"No design was verified: the brief has {missing}. {MARK}stop: no_brief after "
                f"round {note['round']}."
            )
            return act({**note, "stop": "no_brief"}, index, "finish", answer=answer)
        question = (
            f"The design needs a brief, and the problem state has {missing}. Which heating and "
            "cooling demand should the design meet (profile names or daily values), and which "
            "limits (doublets, flow per doublet, brine cooling, supply temperatures)?"
        )
        return act({**note, "missing": missing}, index, "ask_user", question=question)

    async def after_verification(self, context, calls):
        """Check the design again with gemini, then cost it, route its failures, or stop."""
        found = await asyncio.to_thread(verify_design, context)
        round_number = rounds(calls)
        design = context.problem.design.get("reference")
        result = context.problem.verification.get("result")
        index = len(calls)
        if found["passed"]:
            task = economist_task(design, result)
            return act({"round": round_number, "passed": True}, index, "economist", task=task)
        failed = sorted(item["name"] for item in found["failures"])
        history = [note["failures"] for note in notes(context.messages) if "failures" in note]
        note = {"round": round_number, "design": design, "result": result, "failures": failed}
        if round_number >= self._max_rounds:
            return stop(context, {**note, "stop": "max_rounds"}, index)
        if repeated([*history, failed]):
            return stop(context, {**note, "stop": "repeated_failure"}, index)
        brief = routed_brief(round_number + 1, self._max_rounds, design, result, found)
        return act(note, index, "designer", task=brief)


def missing_brief(problem):
    """Return what a design run lacks in the state's brief: the brief, or its demand; else None."""
    brief = problem.brief
    if brief is None:
        return "no brief"
    if brief.demand is None or not (brief.demand.heating or brief.demand.cooling):
        return "no demand"
    return None


def answered_task(context, answer):
    """Return the designer's task after the user answered the driver's question on the brief."""
    request = next(item.content for item in context.messages if item.role == "user")
    return f"{request}\n\nThe user answered the question on the brief: {answer}\n\n{SET_BRIEF}"


def rounds(calls):
    """Return the number of the current round: each round starts with a designer call."""
    return sum(name == "designer" for name, _ in calls)


def verifier_task(context):
    """Return the verifier's task: the design the designer recorded."""
    design = context.problem.design.get("reference") if context.problem.design else None
    if design is None:
        return "The designer recorded no design.reference. Report that no design can be verified."
    return (
        f"Verify {design}: simulate it over the whole demand year, run check_results on that "
        "result and record the verification."
    )


def economist_task(design, result):
    """Return the economist's task: cost the verified run."""
    return f"Cost the verified design {design} on its result {result}."


def explainer_task(context):
    """Return the explainer's task: the request and the verified design."""
    request = next(item.content for item in context.messages if item.role == "user")
    design = context.problem.design.get("reference")
    return f"Explain the verified design {design} for this request:\n\n{request}"


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
    run in the same log. A design that passes is costed by the ``Economist`` and explained by the
    ``Explainer``. The loop stops when gemini's checks pass, at ``max_rounds``, when one round fails
    exactly as the one before, or when an agent asks the user; a token or cost budget is a hook of
    the run. Each stop is written in the driver's step text and in the answer as ``stop: <reason>``.
    A design run needs a brief with a demand in the problem state: when the designer leaves none,
    the driver asks the user and hands the answer back to the designer, and stops with
    ``no_brief`` at ``max_rounds``.
    """

    name = "design"

    def __init__(self, designer, verifier, max_rounds=5):
        """Keep the two agents and the limit; a run starts with the designer."""
        self.designer = designer
        self.verifier = verifier
        self.max_rounds = max_rounds
        self.agent = DesignDriver(designer, verifier, max_rounds)

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

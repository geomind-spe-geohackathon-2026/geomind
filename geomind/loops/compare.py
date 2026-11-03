"""Compare alternative plant families: each designed, verified, then compared and explained."""

import asyncio
import json

from geomind import runtime
from geomind.agents import FamilyDesigner
from geomind.loops.design import (
    DESIGN_TOKENS,
    MARK,
    DesignDriver,
    DesignLoop,
    act,
    answered_task,
    driver_calls,
    missing_case,
    notes,
    project_files_text,
    project_plants_text,
    question_of,
    request_of,
    rounds,
)
from geomind.tools import Delegate
from geomind.types import Action, ToolCall
from geomind.verify.design import verify_design

FEASIBLE = "feasible"
VERIFIED = "verified"
LIMIT_CODE = '"code": "budget"'
SHOWN_REASON = 500
TABLE_COLUMNS = ("family", "verdict", "design", "result", "reason")


class CompareDriver(DesignDriver):
    """Drive a design whose designer compares two or three families with one ``run_study``.

    NOTE: the driver of ``StudyCompareLoop``, kept so a log and a recording of it still run. New
    comparisons use ``ComparisonDriver``.
    """

    def first_task(self, context):
        """Return the designer's first task: the request, and the comparison it must run."""
        return (
            f"{request_of(context)}{project_files_text(context)}\n\n"
            f"Round 1 of at most {self._max_rounds}. Read the case, then "
            "build and size two or three materially different families that gemini can run, "
            "compare them with one run_study (method minimize, prepare size), simulate the best "
            "feasible design for the whole year and check it. Record design.start_result, "
            "design.alternatives, design.study, design.reference and design.result."
        )


class StudyCompareLoop(DesignLoop):
    """Design by comparing families in one study: the ``compare`` loop up to 0.4.5.

    It is a ``DesignLoop`` whose designer is asked for two or three families and compares them
    with one ``run_study``. NOTE: a log and a recording of 0.4.5 and before name this driver, so
    they run on it; a new run takes ``CompareLoop``.
    """

    name = "compare"
    driver = CompareDriver


def plan_instructions(asks):
    """Return what the planning designer does; a run with a user confirms what it proposes."""
    proposal = (
        "confirm them with one ask_user before you hand over"
        if asks
        else 'record each as an assumption {id, text, value, source: "agent", confirmed: false}'
    )
    return (
        "Plan a comparison and build nothing yet. Read the case; when the state has none, fill it "
        "from the project, its files or the request. The alternatives come from the request or "
        "the case, all of them. When neither names any, propose candidates from list_plants (the "
        f"plant classes and the project's plants), a one-line reason each, and {proposal}. Record "
        "them as design.families [{id, summary, status}], status 'blocked' for one gemini cannot "
        "build. Record in design.search the objective, evaluations and seed the user or the case "
        "gave; where they gave none, choose and record each as an assumption."
    )


def plan_task(context, asks):
    """Return the first designer's task: the request, the project and the plan."""
    project = f"{project_plants_text(context)}{project_files_text(context)}"
    return f"{request_of(context)}{project}\n\n{plan_instructions(asks)}"


def family_task(request, family, failed=None, attempt=0):
    """Return the task of one family's nested run, which designs that family and nothing else.

    A retry (``attempt`` 1 and up) is told why gemini rejected the last design, ``failed``.
    """
    prefix = f"{family['id']}_r{attempt}_" if attempt else f"{family['id']}_"
    again = (
        f" An earlier design of this family failed gemini's checks: {failed}. Design it again, "
        "changing what failed."
        if attempt
        else ""
    )
    return (
        f"{request}\n\nDesign one alternative only: {family['id']}: {family['summary']}.{again} "
        "Other runs design the others. Size it, simulate the whole year, check it, optimize it "
        "with design.search, simulate the best and check it. Start every design and study name "
        f"with '{prefix}'. Do not write design.reference, design.result or verification. Add "
        "one entry at /design/alternatives/-: {family, design, result, verdict, reason}, with "
        f"family '{family['id']}' and verdict 'feasible' or 'infeasible', and the reason of an "
        "infeasible one. When the family cannot be built, add it as 'infeasible' with why."
    )


def cell(value):
    """Return a value as a table cell: one line, without the column mark."""
    return "" if value is None else str(value).replace("|", "/").replace("\n", " ")


def alternatives_table(design):
    """Return the alternatives of ``design`` as a Markdown table, or ``""``.

    An entry without a verdict is the form before 0.4.6: a state of such entries has no table.
    """
    entries = (design or {}).get("alternatives") or ()
    if not any("verdict" in item for item in entries):
        return ""
    rows = [f"| {' | '.join(TABLE_COLUMNS)} |", "|" + " --- |" * len(TABLE_COLUMNS)]
    for item in entries:
        rows.append(f"| {' | '.join(cell(item.get(name)) for name in TABLE_COLUMNS)} |")
    return "\n".join(rows)


def has_entry(design, family):
    """Tell whether a family has its alternative in the state."""
    return any(item.get("family") == family for item in design.get("alternatives") or ())


def open_families(design):
    """Return the families to design: every recorded one that is not blocked."""
    return [item for item in design.get("families") or () if item.get("status") != "blocked"]


def blocked_entries(design):
    """Return an alternative for each blocked family, with the family's summary as the reason."""
    return [
        {"family": item.get("id"), "verdict": "blocked", "reason": item.get("summary")}
        for item in design.get("families") or ()
        if item.get("status") == "blocked"
    ]


def attempted(messages):
    """Return the ids of the families a batch has already run."""
    return [family for note in notes(messages) for family in note.get("batch", ())]


def with_verdict(design, verdict):
    """Return the alternatives of a verdict, in order."""
    return [item for item in design.get("alternatives") or () if item.get("verdict") == verdict]


def verdict_changes(design, family, verdict, reason):
    """Return the patch that sets the verdict and the reason of a family.

    NOTE: a patch addresses a list item by its ``id`` and an alternative has none, so the list is
    replaced whole; the driver alone writes it once the family runs ended.
    """
    entries = [
        {**item, "verdict": verdict, "reason": reason} if item.get("family") == family else item
        for item in design.get("alternatives") or ()
    ]
    return [{"op": "add", "path": "/design/alternatives", "value": entries}]


def selected_changes(item):
    """Return the patch that makes an alternative the design the state names."""
    return [
        {"op": "add", "path": "/design/reference", "value": item["design"]},
        {"op": "add", "path": "/design/result", "value": item["result"]},
        {"op": "add", "path": "/verification", "value": {"result": item["result"]}},
    ]


def cleared_changes(problem):
    """Return the patch that leaves no design for the user: nothing was verified."""
    design = problem.design or {}
    changes = [
        {"op": "remove", "path": f"/design/{name}"}
        for name in ("reference", "result")
        if name in design
    ]
    if "result" in (problem.verification or {}):
        changes.append({"op": "remove", "path": "/verification/result"})
    return changes


def failure_reason(found):
    """Return why gemini's verdict failed, on one line."""
    failed = ", ".join(f"{item['name']}: {item['detail']}" for item in found["failures"])
    return found.get("reason") or failed


def recommended(design):
    """Return the verified alternative the economist recommends, else the first verified."""
    verified = with_verdict(design, VERIFIED)
    chosen = (design.get("comparison") or {}).get("recommended")
    return next((item for item in verified if item.get("family") == chosen), verified[0])


def economist_comparison_task(context):
    """Return the economist's task: compare every verified design with gemini."""
    design = context.problem.design or {}
    runs = ", ".join(
        f"{item['family']} {item['result']}" for item in with_verdict(design, VERIFIED)
    )
    return (
        f"The request:\n\n{request_of(context)}\n\n"
        "Compare the verified designs, family and result: "
        f"{runs}, with compare, by the objectives the request names, else design.search. Record "
        "/design/comparison: {by, ranking: [{family, rank, pareto}], recommended}, gemini's "
        "ranking and Pareto set, recommended the family you recommend. Run sample_uncertainty or "
        "sensitivity only when the request asks for them, and then only on the top designs."
    )


def explanation_task(context):
    """Return the explainer's task: the table of every family and the comparison."""
    design = context.problem.design or {}
    comparison = json.dumps(design.get("comparison") or {}, ensure_ascii=False)
    return (
        f"Write the comparison for this request:\n\n{request_of(context)}\n\nEvery family:\n\n"
        f"{alternatives_table(design)}\n\nThe comparison: {comparison}\n\nGive the table of every "
        "family, feasible or not and why, the ranking, the Pareto set, the recommended design and "
        "why, and what was assumed. With no verified design, say so and recommend none."
    )


class ComparisonDriver(DesignDriver):
    """Drive a comparison: plan, one nested run per family, one check per design, then the rest.

    NOTE: every family runs in a nested run of its own, side by side up to the loop's
    ``concurrency``, unset being one at a time, so one that fails stops nothing. ``update_state``
    is the shared record: a family adds its one entry, and the driver moves the state's design to
    each family it verifies, then to the recommended one, so the ``Verified`` hook judges that.
    """

    def __init__(self, designer=None, verifier=None, max_rounds=5):
        """Declare the agents of the design loop and the run of one family."""
        super().__init__(designer, verifier, max_rounds)

        # Tools
        self.family_designer = Delegate(
            FamilyDesigner(), max_summary_tokens=DESIGN_TOKENS, runs_beside=True
        )

        self._concurrency = None
        self._asks = False
        self._retries = None

    def load_loop_state(self, state):
        """Take the logged limit, the concurrency and whether a user can answer."""
        super().load_loop_state(state)
        self._concurrency = state.get("concurrency", self._concurrency)
        self._asks = state.get("asks", self._asks)
        self._retries = state.get("retries", self._retries)

    def batch_size(self):
        """Return how many families run together: one while a run may wait for a user."""
        return 1 if self._asks or not self._concurrency else self._concurrency

    def first_task(self, context):
        """Return the first designer's task: the plan of the comparison."""
        return plan_task(context, self._asks)

    async def forward(self, context):
        """Decide the next move from the calls so far and the state."""
        calls = driver_calls(context.messages)
        index = len(calls)
        note = {"round": max(rounds(calls), 1)}
        if not calls:
            return self.begin(context, note, index)
        name, output = calls[-1]
        if name == "ask_user":
            task = f"{answered_task(context, output)}\n\n{plan_instructions(self._asks)}"
            return act(note, index, "designer", task=task)
        if name == "designer":
            return self.after_plan(context, note, index)
        if name == "verifier":
            return await self.after_check(context, note, index)
        if name == "family_designer":
            return self.after_batch(context, calls, note, index)
        return self.next_move(context, calls, note, index)

    def after_plan(self, context, note, index):
        """Record the blocked families and go on, or say what the comparison lacks."""
        missing = missing_case(context.problem)
        if missing is not None and note["round"] >= self._max_rounds:
            return self.stopped(note, index, "no_case", f"the problem state has {missing}")
        if missing is not None:
            return act(note, index, "ask_user", question=question_of(missing))
        design = context.problem.design or {}
        if not design.get("families"):
            return self.stopped(note, index, "no_alternatives", "no alternative was recorded")
        known = design.get("alternatives") or []
        value = [*known, *blocked_entries(design)]
        changes = [{"op": "add", "path": "/design/alternatives", "value": value}]
        return act(note, index, "update_state", changes=changes)

    def stopped(self, note, index, reason, why):
        """Return the move that ends a comparison that has nothing to compare."""
        answer = f"No comparison: {why}. {MARK}stop: {reason}."
        return act({**note, "stop": reason}, index, "finish", answer=answer)

    def after_batch(self, context, calls, note, index):
        """Record each family of the batch that left no entry, with why, then go on."""
        design = context.problem.design or {}
        batch = notes(context.messages)[-1]["batch"]
        outputs = [output for _, output in calls[-len(batch) :]]
        missing = [
            {
                "family": family,
                "verdict": "failed",
                "reason": output[:SHOWN_REASON],
            }
            for family, output in zip(batch, outputs)
            if not has_entry(design, family)
        ]
        limited = any(LIMIT_CODE in output for output in outputs)
        changes = [
            {"op": "add", "path": "/design/alternatives/-", "value": item} for item in missing
        ]
        if changes:
            return act({**note, "limited": limited}, index, "update_state", changes=changes)
        return self.next_move(context, calls, {**note, "limited": limited}, index)

    def next_move(self, context, calls, note, index):
        """Run the next batch, check the next design, or end the comparison."""
        design = context.problem.design or {}
        last = notes(context.messages)[-1]
        if last.get("limited") or note.get("limited"):
            return self.partial(design, note, index)
        if "retry" in last:
            return self.retry(context, last, note, index)
        done = attempted(context.messages)
        pending = [item for item in open_families(design) if item.get("id") not in done]
        if pending:
            return self.batch(context, pending, note, index)
        return self.check_next(context, calls, design, note, index)

    def partial(self, design, note, index):
        """End on a limit: the finished alternatives are the answer."""
        answer = (
            "The comparison stopped at its limit, so this is a partial answer.\n\n"
            f"{alternatives_table(design)}\n\n{MARK}stop: limit."
        )
        return act({**note, "stop": "limit"}, index, "finish", answer=answer)

    def batch(self, context, pending, note, index):
        """Return one step of family runs, as many as the concurrency allows."""
        families = pending[: self.batch_size()]
        request = request_of(context)
        calls = tuple(
            ToolCall(
                id=f"loop-{index}-family-{position}",
                name="family_designer",
                input={"task": family_task(request, family)},
            )
            for position, family in enumerate(families)
        )
        text = MARK + json.dumps({**note, "batch": [item["id"] for item in families]})
        return Action(text=text, tool_calls=calls)

    def check_next(self, context, calls, design, note, index):
        """Check the next feasible design, or go on to the comparison."""
        last = notes(context.messages)[-1]
        waiting = with_verdict(design, FEASIBLE)
        if not waiting:
            return self.conclude(context, calls, design, note, index)
        item = waiting[0]
        family = item["family"]
        if not (item.get("design") and item.get("result")):
            changes = verdict_changes(
                design, family, "failed", "the run recorded no design and result"
            )
            return act(note, index, "update_state", changes=changes)
        if last.get("selected") != family:
            changes = selected_changes(item)
            return act({**note, "selected": family}, index, "update_state", changes=changes)
        task = (
            f"Verify {item['design']}: run check_results once on its result {item['result']} and "
            "record the verification."
        )
        return act({**note, "checking": family}, index, "verifier", task=task)

    async def after_check(self, context, note, index):
        """Record gemini's verdict on the family just checked, or set it aside for a retry."""
        found = await asyncio.to_thread(verify_design, context)
        family = notes(context.messages)[-1]["checking"]
        verdict = VERIFIED if found["passed"] else "rejected"
        reason = None if found["passed"] else failure_reason(found)
        design = context.problem.design or {}
        used = sum(item.get("retry") == family for item in notes(context.messages))
        if verdict == "rejected" and used < (self._retries or 0):
            kept = [
                item for item in design.get("alternatives") or () if item.get("family") != family
            ]
            changes = [{"op": "add", "path": "/design/alternatives", "value": kept}]
            retry = {**note, "retry": family, "failed": reason, "attempt": used + 1}
            return act(retry, index, "update_state", changes=changes)
        changes = verdict_changes(design, family, verdict, reason)
        return act(note, index, "update_state", changes=changes)

    def retry(self, context, last, note, index):
        """Run a rejected family again, told why gemini rejected it."""
        design = context.problem.design or {}
        family = next(
            item for item in design.get("families") or () if item.get("id") == last["retry"]
        )
        task = family_task(request_of(context), family, last["failed"], last["attempt"])
        call = ToolCall(
            id=f"loop-{index}-family-retry", name="family_designer", input={"task": task}
        )
        text = MARK + json.dumps({**note, "batch": [family["id"]]})
        return Action(text=text, tool_calls=(call,))

    def conclude(self, context, calls, design, note, index):
        """Compare the verified designs, name the recommended one, explain, and finish."""
        called = {name for name, _ in calls}
        has_verified = bool(with_verdict(design, VERIFIED))
        if has_verified and "economist" not in called:
            task = economist_comparison_task(context)
            return act(note, index, "economist", task=task)
        marks = notes(context.messages)
        if "explainer" not in called and not any("final" in item for item in marks):
            final = {**note, "final": has_verified}
            changes = (
                selected_changes(recommended(design))
                if has_verified
                else cleared_changes(context.problem)
            )
            if changes:
                return act(final, index, "update_state", changes=changes)
        if "explainer" not in called:
            return act(note, index, "explainer", task=explanation_task(context))
        output = calls[-1][1]
        reason = "compared" if has_verified else "no_verified"
        answer = f"{output}\n\n{MARK}stop: {reason}"
        return act({**note, "stop": reason}, index, "finish", answer=answer)


class CompareLoop(DesignLoop):
    """Compare families: plan, design each alone, verify each, compare, explain.

    The families come from the request or the case, else the ``Designer`` proposes them, and a
    user confirms them unless the run is ``auto``, where they are unconfirmed assumptions. One
    ``FamilyDesigner`` nested run per family designs it, ``concurrency`` of them side by side
    (the setting ``compare_concurrency``; unset, one at a time); a failed or infeasible family
    stops nothing and keeps its reason. The ``Verifier`` checks each feasible design; one gemini
    rejects runs again, told why, up to ``retries`` times (setting ``compare_retries``; unset, no
    retry). The
    ``Economist`` compares the verified ones and the ``Explainer`` writes the comparison.
    Budgets and time limits are hooks of the run, shared by its nested runs. A stop gives a
    partial answer listing the finished alternatives.
    """

    name = "compare"
    driver = ComparisonDriver

    def __init__(self, designer, verifier, max_rounds=5, concurrency=None, retries=None):
        """Keep the agents and the limits; the settings give what is not given."""
        super().__init__(designer, verifier, max_rounds)
        self.concurrency = concurrency or runtime.get("compare_concurrency")
        self.retries = retries if retries is not None else runtime.get("compare_retries")
        self.asks = False
        self.agent.load_loop_state(self.state_dict())

    def guard(self, engine):
        """Register the hook, and note whether a user can answer in this run."""
        super().guard(engine)
        self.asks = engine.permissions.mode == "ask"
        self.agent.load_loop_state(self.state_dict())

    def state_dict(self):
        """Return the limit, the concurrency and whether a user can answer."""
        return {
            **super().state_dict(),
            "concurrency": self.concurrency,
            "asks": self.asks,
            "retries": self.retries,
        }

    def load_state_dict(self, state):
        """Take the logged settings; a log without one keeps this loop's."""
        super().load_state_dict(state)
        self.concurrency = state.get("concurrency", self.concurrency)
        self.asks = state.get("asks", self.asks)
        self.retries = state.get("retries", self.retries)

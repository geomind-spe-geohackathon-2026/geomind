"""The reviewer as the project lead's tool, with gemini's check run again by code after it."""

import json

from geomind import runtime
from geomind.agents.project.reviewer import Reviewer
from geomind.tools import Delegate
from geomind.tools.memory import keep_design
from geomind.types import Request
from geomind.verify.design import verify_design

REVIEW_TOKENS = 1500
"""The most tokens of the reviewer's report the project lead reads back."""
VERDICT = "gemini verdict: "
"""How the code's verdict starts in the review's output, so a later review finds it."""
DOMAINS = (
    ("subsurface", "design_lead (reservoir and well engineers)"),
    ("surface", "design_lead (energy systems and integration engineers)"),
    ("sizing", "design_lead (resize, keep the topology)"),
    ("coupled", "design_lead (coupled: subsurface first, then surface)"),
    ("case", "case_lead"),
)
"""Where a failure of each gemini domain goes first: a hint to the project lead, not a rule."""


def owner_hint(domain):
    """Return who a failure of ``domain`` goes to first."""
    return next((owner for name, owner in DOMAINS if name == domain), "design_lead")


def earlier_verdicts(context):
    """Return the verdicts earlier reviews of this run wrote, oldest first."""
    found = []
    for message in context.messages:
        if message.role != "tool" or VERDICT not in str(message.content):
            continue
        line = str(message.content).split(VERDICT, 1)[1].splitlines()[0]
        found.append(json.loads(line))
    return found


def verdict_of(found, design):
    """Return the code's verdict of one review, as the next review reads it."""
    failures = sorted((item["name"], item["domain"], item["detail"]) for item in found["failures"])
    return {"design": design, "passed": found["passed"], "failures": failures}


def verdict_text(verdict, earlier):
    """Return the verdict for the project lead: the failures by owner, and a repeat flagged."""
    lines = [VERDICT + json.dumps(verdict)]
    for name, domain, detail in verdict["failures"]:
        lines.append(f"- {name} ({domain}, to {owner_hint(domain)}): {detail}")
    names = [name for name, _, _ in verdict["failures"]]
    repeated = [
        item
        for item in earlier
        if not item["passed"]
        and [name for name, _, _ in item["failures"]] == names
        and item["design"] != verdict["design"]
    ]
    if names and repeated:
        lines.append(
            "repeated_failure: a changed design failed exactly as before; stop and report what "
            "was tried, unless a real change of approach is left"
        )
    return "\n".join(lines)


class Review(Delegate):
    """Have the reviewer check the final design, then check it again with gemini in code.

    NOTE: the verdict is gemini's, never the model's: after the reviewer's nested run the code runs
    ``verify_design`` on the state's design, sorts each failure by its domain to the owner it goes
    to first (a hint), flags a failure that repeats on a changed design, and keeps a design that
    passed as experience (code alone writes designs, after the reviewer passed them).
    """

    def __init__(self):
        """Offer the reviewer as ``reviewer``."""
        super().__init__(Reviewer(), max_summary_tokens=REVIEW_TOKENS)

    async def _delegate(self, context, task):
        """Run the reviewer, then gemini's check on the state as it now stands."""
        report = await super()._delegate(context, task)
        if isinstance(report, Request):
            return report
        fresh = context.session.context()
        found = await runtime.in_gemini_thread(verify_design, fresh)
        verdict = verdict_of(found, fresh.problem.design_state.reference)
        if found["passed"]:
            rejected = [
                [name for name, _, _ in item["failures"]]
                for item in earlier_verdicts(fresh)
                if not item["passed"]
            ]
            await runtime.in_gemini_thread(keep_design, fresh, found, rejected)
        return f"{report}\n\n{verdict_text(verdict, earlier_verdicts(fresh))}"

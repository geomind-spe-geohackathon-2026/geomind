"""Next-step suggestions: what the user may do after an answer, chosen by code from the stage.

The stage comes from the problem state: no case, a case without a plant, a plant without a
result, or a result. Each stage has its steps, each a ``{label, message}`` in English:
``label`` is what a button shows, ``message`` what the app sends as the user's next
message. The project lead may reword, reorder or replace one through its ``finish``; code keeps
only what fits the limits and names a step the app can run, else the stage's own list.
"""

import re
from typing import Any

from geomind.tools.base import tool
from geomind.types import Finish

MAX_SUGGESTIONS = 3
MAX_LABEL = 40
MAX_MESSAGE = 200
ARABIC_SCRIPT = re.compile("[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")
"""Arabic-script letters. Suggestions are English only (Sahand, 2026-11-04): a proposed one in
another script is refused and the stage's own list is shown."""

STEPS = {
    "case_from_files": {
        "en": (
            "Build the case from my files",
            "Set the case of the design from the project's files.",
        ),
    },
    "case_by_questions": {
        "en": ("Build the case by questions", "Set the case by asking me for each value it needs."),
    },
    "files_needed": {
        "en": ("Which files do you need?", "Which files should I add so you can set the case?"),
    },
    "set_economics": {
        "en": ("Set the economics", "Set up the economics of this case."),
    },
    "design_plant": {
        "en": ("Design a plant", "Design a plant for this case and check it with gemini."),
    },
    "check_case": {
        "en": (
            "Check the case and its sources",
            "Check the case and list every value that has no source yet.",
        ),
    },
    "compare_options": {
        "en": ("Compare plant options", "Design and compare a few plant options for this case."),
    },
    "optimise": {
        "en": ("Optimise the design", "Optimise the design and simulate the best one."),
    },
    "economics": {
        "en": ("Costs and economics", "Estimate the costs and the economics of the design."),
    },
    "check_design": {
        "en": ("Check the design", "Check the design against the case's requirements."),
    },
    "report": {
        "en": ("Write the report", "Write the report of the design and its results."),
    },
    "sensitivity": {
        "en": ("Sensitivity analysis", "Run a sensitivity analysis on the design's main inputs."),
    },
    "explain": {
        "en": ("Explain the results", "Explain the results of the design in plain words."),
    },
    "rerun_study": {
        "en": ("Run the study again", "The case changed after the study: run the study again."),
    },
    "wait_study": {
        "en": ("Is the study done?", "Tell me when the running study is done, and what it found."),
    },
    "uncertainty": {
        "en": (
            "Uncertainty of the results",
            "Run an uncertainty analysis of the design's results.",
        ),
    },
    "structure_search": {
        "en": ("Search other plant layouts", "Search other plant layouts with a structure study."),
    },
    "other_objective": {
        "en": (
            "Optimise for CO2 instead",
            "Optimise the design for CO2 instead of cost, and compare.",
        ),
    },
    "other_case": {
        "en": (
            "Test against another case",
            "Check the design against another case: a colder year or other prices.",
        ),
    },
    "finish_item": {
        "en": ("Finish the {label}", "Finish the {label}."),
    },
}
"""Every step the app can run, with its label and message in English.

``finish_item`` names an incomplete item of the project by its label.
"""

STAGES = {
    "no_case": ("case_from_files", "case_by_questions", "files_needed"),
    "case": ("design_plant", "check_case", "compare_options"),
    "plant": ("optimise", "economics", "check_design"),
    "result": ("report", "sensitivity", "explain"),
    "report": ("report", "explain", "sensitivity"),
    "more": ("uncertainty", "structure_search", "other_objective", "other_case"),
}
"""The steps of each stage, in their order: ``no_case`` to ``result`` from a chat's state,
``no_case`` to ``more`` from a project's (``Workspace.project_state``)."""
ITEMS = ("case", "plant", "study", "results", "report")
"""The parts of a project's state, in the order the work makes them."""


def _field(problem, name):
    """Return a field of a problem state or of its dict."""
    return problem.get(name) if isinstance(problem, dict) else getattr(problem, name)


def stage_of(problem):
    """Return the stage of a problem state: ``no_case``, ``case``, ``plant`` or ``result``."""
    if not _field(problem, "case"):
        return "no_case"
    design = _field(problem, "design") or {}
    if not design.get("reference"):
        return "case"
    if design.get("result") or _field(problem, "results"):
        return "result"
    return "plant"


def economics_unset(problem, project=None):
    """Tell whether the case is known to have no economics yet (QA-194).

    A project's ``economics`` state, when its workspace gives one, decides; else the chat's case,
    when it has one, without an ``economics`` section. Unknown is not unset.
    """
    if project and project.get("economics") is not None:
        return state_of(project.get("economics")) not in ("done", "ready")
    case = _field(problem, "case") if problem is not None else None
    return isinstance(case, dict) and bool(case) and not case.get("economics")


def stage_steps(problem, files):
    """Return the step names of a chat's stage; without files, no case is built from files.

    A case without economics asks for them first: a cost-based design or study stops on them.
    """
    stage = stage_of(problem)
    steps = STAGES[stage]
    if stage == "case" and economics_unset(problem):
        steps = ("set_economics", *steps)
    return tuple(step for step in steps if step != "case_from_files" or files)


def state_of(item):
    """Return the state of one item of a project: a string, or the ``state`` of a dict."""
    return item.get("state") if isinstance(item, dict) else item


def project_stage(project):
    """Return a project's stage: ``no_case``, ``case``, ``plant``, ``report`` or ``more``.

    The case not done or ready (a set case is ``ready``, QA-023): build it; the plant not done
    or ready: design it; the study or its
    results not done: study it; the report not done: report; all done: more studies.
    """
    if state_of(project.get("case")) not in ("done", "ready"):
        return "no_case"
    if state_of(project.get("plant")) not in ("done", "ready"):
        return "case"
    if state_of(project.get("study")) != "done" or state_of(project.get("results")) != "done":
        return "plant"
    if state_of(project.get("report")) != "done":
        return "report"
    return "more"


def project_steps(project, files, problem=None):
    """Return the step names a project's state gives, the most urgent first.

    A case changed after the study asks for the study again first, an incomplete item to be
    finished; a running study gives no study chip, but waiting or explaining. A ready case
    without economics asks for them before a plant (QA-194).
    """
    stage = project_stage(project)
    steps = [step for step in STAGES[stage] if step != "case_from_files" or files]
    if stage == "case" and economics_unset(problem, project):
        steps.insert(0, "set_economics")
    if state_of(project.get("study")) == "running":
        steps = ["wait_study", "explain"] + [step for step in steps if step != "optimise"]
    urgent = ["rerun_study"] if project.get("case_changed_after_study") else []
    if any(state_of(project.get(item)) == "incomplete" for item in ITEMS):
        urgent.append("finish_item")
    return tuple(dict.fromkeys(urgent + steps))


def incomplete_label(project):
    """Return the label of the first incomplete item of a project, by its ``label`` or name."""
    for item in ITEMS:
        value = project.get(item)
        if state_of(value) == "incomplete":
            return (value.get("label") if isinstance(value, dict) else None) or item
    return ""


def shown(step, item=""):
    """Return one step as ``{label, message}``; ``item`` fills ``{label}``."""
    label, message = STEPS[step]["en"]
    label = label.format(label=item)[:MAX_LABEL]
    return {"label": label, "message": message.format(label=item)[:MAX_MESSAGE]}


def _fits(item):
    """Tell whether a proposed suggestion has a known step, fits the limits and is English."""
    if not isinstance(item, dict) or item.get("step") not in STEPS:
        return False
    label, message = item.get("label"), item.get("message")
    if not isinstance(label, str) or not isinstance(message, str):
        return False
    if not 0 < len(label.strip()) <= MAX_LABEL or not 0 < len(message.strip()) <= MAX_MESSAGE:
        return False
    return not ARABIC_SCRIPT.search(label + message)


def checked(proposed, steps):
    """Return the proposed suggestions that fit, as ``[(step, item)]``.

    A step appears once; at most one step that is not the stage's own replaces one of them.
    """
    kept, seen, foreign = [], set(), 0
    for item in proposed or ():
        if not _fits(item) or item["step"] in seen:
            continue
        if item["step"] not in steps:
            if foreign:
                continue
            foreign += 1
        seen.add(item["step"])
        kept.append(
            (item["step"], {"label": item["label"].strip(), "message": item["message"].strip()})
        )
    return kept[:MAX_SUGGESTIONS]


def next_steps(problem, files, user_text, proposed=None, project=None):
    """Return the suggestions after an answer: the lead's that fit first, then the stage's.

    ``project`` is ``Workspace.project_state``'s dict: the stage follows the project then, and
    the chat's problem state only without one. The lead's suggestions reword, reorder or replace
    the stage's steps; the stage's own steps not named fill the list up to ``MAX_SUGGESTIONS``
    (QA-204: one proposed step had dropped the other two). Suggestions are English whatever
    ``user_text``'s language; the engine still passes it.
    """
    steps = project_steps(project, files, problem) if project else stage_steps(problem, files)
    kept = checked(proposed, steps)
    label = incomplete_label(project) if project else ""
    taken = {step for step, _ in kept}
    filled = [item for _, item in kept]
    for step in steps:
        if len(filled) >= MAX_SUGGESTIONS:
            break
        if step not in taken:
            filled.append(shown(step, label))
    return filled


def suggest(problem, files, project=None):
    """Return the suggestions of an empty chat, before the first message: no model is called.

    ``problem`` is a ``ProblemState`` or its dict, ``files`` the names of the project's files,
    ``project`` the project's state (``Workspace.project_state``), which decides the stage when
    given.
    """
    goal = _field(problem, "goal") if problem is not None else ""
    state = problem if problem is not None else {"case": None}
    return next_steps(state, files, goal or "", project=project)


@tool(effect="read", runs_alone=True)
async def finish(answer: Any, suggestions: list[dict[str, str]] | None = None):
    """End the run with the final answer and, if you want, the next steps you suggest.

    ``suggestions`` are at most three ``{step, label, message}``, in English:
    ``step`` is one of case_from_files, case_by_questions, files_needed, set_economics, design_plant,
    check_case, compare_options, optimise, economics, check_design, report, sensitivity,
    explain, rerun_study, wait_study, uncertainty, structure_search, other_objective,
    other_case; ``label`` at most 40 characters, ``message`` (what the user sends when they pick
    it) at most 200. Code keeps those that fit, with at most one step that is not of the
    stage's own (so ``other_case``, a step after the results, rarely), and fills the rest with the
    stage's own steps.
    """
    return Finish(answer=answer, suggestions=suggestions)

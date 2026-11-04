"""A value is asked once per run tree: a question about case paths already answered is not asked.

The run: the design lead asked for ``site.air.pressure`` and the user answered ``unknown``; the
project lead then had the case lead ask for it again. A tool's question names case paths
(``site.air.pressure``); when an earlier answered question of the same tree named exactly the
same paths, the earlier answer is the result, and the user is not asked again. The asked
questions and their answers come from the root's log, so this holds across resumes.
"""

import re

CASE_SECTIONS = (
    "time",
    "site",
    "demand",
    "utilities",
    "requirements",
    "economics",
    "initial_state",
)
"""The case sections whose dotted paths a question names."""
PATH = re.compile(rf"\b(?:{'|'.join(CASE_SECTIONS)})(?:\.[A-Za-z_][A-Za-z0-9_]*)+")


def named_paths(text):
    """Return the case paths a question names, such as ``site.air.pressure``."""
    return frozenset(match.group(0) for match in PATH.finditer(text or ""))


def _answer_text(output):
    """Return the user's text of an answer result, also of a tool that acts on its answer."""
    if isinstance(output, dict) and isinstance(output.get("answer"), str):
        return output["answer"]
    return output if isinstance(output, str) else None


def earlier_answer(events, request):
    """Return ``(earlier request, answer text)`` of the last answered question on the same paths.

    Only a question names paths; a question naming none, or one whose paths no earlier question
    named exactly, is asked.
    """
    paths = named_paths(request.message) if request.kind == "question" else frozenset()
    if not paths:
        return None
    asked, found = {}, None
    for event in events:
        if event.type == "request" and event.point == "tool" and event.request.kind == "question":
            asked[(event.run_id, event.request.call_id)] = event.request
            continue
        if event.type != "tool.result" or event.source != "answer":
            continue
        earlier = asked.get((event.run_id, event.call_id))
        text = _answer_text(event.output)
        if earlier is not None and text is not None and named_paths(earlier.message) == paths:
            found = (earlier, text)
    return found


def reused_answer(earlier, text):
    """Return what the model reads instead of a question the user already answered."""
    paths = ", ".join(sorted(named_paths(earlier.message)))
    return (
        f"Not asked again: the user already answered a question on {paths} in this run "
        f"({earlier.id}): {text!r}. Take that answer; a value it does not give stays open"
    )

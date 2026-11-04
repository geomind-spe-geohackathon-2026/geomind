"""A value is asked once per run tree: a question about case paths already answered is not asked.

The run: the design lead asked for ``site.air.pressure`` and the user answered ``unknown``; the
project lead then had the case lead ask for it again. A tool's question names case paths
(``site.air.pressure``); a path an earlier answered question of the same tree named, alone or
among others, is answered. A question whose every path is answered is not asked: the earlier
answers are its result. A question with new paths too is asked with the earlier answers under it,
and only the new paths to answer. The asked
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


def answered_paths(events, request):
    """Return ``{path: (earlier request, answer text)}`` of the paths of ``request`` answered.

    A path counts as answered by the first answered question of the tree that named it, alone or
    among others (the run: ``site.air.pressure`` was item 4 of a 19-item question, answered
    ``unknown``, and asked again on its own). Only a question names paths; one naming none has none.
    """
    paths = named_paths(request.message) if request.kind == "question" else frozenset()
    if not paths:
        return {}
    asked, found = {}, {}
    for event in events:
        if event.type == "request" and event.point == "tool" and event.request.kind == "question":
            asked[(event.run_id, event.request.call_id)] = event.request
            continue
        if event.type != "tool.result" or event.source != "answer":
            continue
        earlier = asked.get((event.run_id, event.call_id))
        text = _answer_text(event.output)
        if earlier is None or text is None:
            continue
        for path in named_paths(earlier.message) & paths:
            found.setdefault(path, (earlier, text))
    return found


def _by_question(found):
    """Return ``[(earlier request, answer text, its paths)]`` of ``answered_paths``, in order."""
    grouped = {}
    for path, (earlier, text) in sorted(found.items()):
        grouped.setdefault(earlier.id, (earlier, text, []))[2].append(path)
    return list(grouped.values())


def reused_answer(found):
    """Return what the model reads instead of a question whose every path was answered before."""
    parts = [
        f"on {', '.join(paths)} ({earlier.id}): {text!r}"
        for earlier, text, paths in _by_question(found)
    ]
    return (
        f"Not asked again: the user already answered a question {'; and '.join(parts)} in this "
        "run. Take that answer; a value it does not give stays open"
    )


def asking_new(request, found):
    """Return ``request`` that asks only the paths not answered before, the earlier answers with it.

    The question keeps its text; a line under it gives each earlier answer and names the paths
    the user answers now.
    """
    new = sorted(named_paths(request.message) - set(found))
    earlier = "; ".join(
        f"{', '.join(paths)} ({question.id}): {text!r}"
        for question, text, paths in _by_question(found)
    )
    note = (
        f"\n\nAlready answered in this run, not asked again: {earlier}. "
        f"Answer only {', '.join(new)}."
    )
    return request.model_copy(update={"message": request.message + note})

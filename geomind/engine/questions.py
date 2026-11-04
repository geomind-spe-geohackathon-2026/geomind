"""A value is asked once per run tree: the same question about the same value is not asked again.

The run: the design lead asked for ``site.air.pressure`` and the user answered ``unknown``; the
project lead then had the case lead ask for it again. A tool's question names case paths
(``site.air.pressure``, or ``.H2S`` and ``C2H6`` shortened in a list after a full path); a path an
earlier answered question of the same tree named, alone or among others, is answered, unless the
new question offers a value for it the earlier one did not (E2E-3, E2E-7, E2E-11: the user
answered "use the nearest city's weather data", the lead fetched it and asks to confirm the
value). A question whose every path is answered is not asked: the earlier answers are its result.
A question with other paths too is asked with the earlier answers under it. The asked questions
and their answers come from the root's log, so this holds across resumes.
"""

import re
from dataclasses import dataclass

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
SHORT = re.compile(
    r"\s*(?:(?P<sep>[,/])|\s(?:and|or)\s)\s*(?P<dot>\.)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?![.\w])"
)
"""A list item after a path: ``, .H2S`` or ``and .return_pressure``; ``, C2H6`` or ``/ CO2``."""
BARE_END = re.compile(r"\s*(?:[,;/)—–]|\n|$|\s(?:and|or)\s)")
"""What follows a list item without its dot: the next item or the list's end, not a sentence."""
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
"""A number of the text, not a digit of a name such as ``N2`` or ``C2H6``."""
CONFIRM = re.compile(r"\bconfirm", re.IGNORECASE)


@dataclass(frozen=True)
class Offer:
    """What a question says about one path: the numbers after it and whether it asks to confirm."""

    numbers: frozenset = frozenset()
    confirm: bool = False

    def __bool__(self):
        """Return whether the question gives a number or asks to confirm."""
        return bool(self.numbers) or self.confirm

    def news(self, earlier):
        """Return whether this offer gives a value or a confirmation ``earlier`` did not."""
        return bool(self.numbers - earlier.numbers) or (self.confirm and not earlier.confirm)


def _shortened(text, match):
    """Yield ``(path, start, end)`` of the list items shortened after the path ``match``."""
    parent = match.group(0).rsplit(".", 1)[0]
    end = match.end()
    while item := SHORT.match(text, end):
        if not item.group("dot") and not (item.group("sep") and BARE_END.match(text, item.end())):
            return
        yield f"{parent}.{item.group('key')}", item.start("key"), item.end()
        end = item.end()


def _mentions(text):
    """Return ``[(path, start, end)]`` of the paths a question names, in order."""
    found = []
    for match in PATH.finditer(text or ""):
        found.append((match.group(0), match.start(), match.end()))
        found.extend(_shortened(text, match))
    return sorted(set(found), key=lambda mention: mention[1])


def offers(text):
    """Return ``{path: Offer}`` of the text after each named path, to the next one or line end."""
    mentions = _mentions(text)
    starts = [start for _, start, _ in mentions[1:]] + [len(text)] if mentions else []
    found = {}
    for (path, _, end), following in zip(mentions, starts, strict=True):
        line = text.find("\n", end)
        part = text[end : min(following, line if line >= 0 else following)]
        old = found.get(path, Offer())
        found[path] = Offer(
            old.numbers | {number.group(0) for number in NUMBER.finditer(part)},
            old.confirm or bool(CONFIRM.search(part)),
        )
    return found


def named_paths(text):
    """Return the case paths a question names, such as ``site.air.pressure``."""
    return frozenset(path for path, _, _ in _mentions(text))


def _answer_text(output):
    """Return the user's text of an answer result, also of a tool that acts on its answer."""
    if isinstance(output, dict) and isinstance(output.get("answer"), str):
        return output["answer"]
    return output if isinstance(output, str) else None


def answered_paths(events, request):
    """Return ``{path: (earlier request, answer text)}`` of the paths of ``request`` answered.

    A path counts as answered by the first answered question of the tree that named it, alone or
    among others (the run: ``site.air.pressure`` was item 4 of a 19-item question, answered
    ``unknown``, and asked again on its own), and offered no less for it: a value or a
    confirmation the earlier question did not offer is a new question. Only a question names
    paths; one naming none has none.
    """
    now = offers(request.message) if request.kind == "question" else {}
    if not now:
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
        for path, offer in offers(earlier.message).items():
            if path in now and not now[path].news(offer):
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
        "run. Take that answer. A value found since (from the source the answer names, a file or "
        "a server) is a new question: ask to confirm it, naming the path, the value and its source"
    )


def _only_paths(text):
    """Return whether every line of the text names a path and none offers a value."""
    lines = [line for line in text.splitlines() if line.strip()]
    return all(named_paths(line) for line in lines) and not any(offers(text).values())


def asking_new(request, found):
    """Return ``request`` with the earlier answers under it.

    The question keeps its text; a line under it gives each earlier answer. Only a question that
    is nothing but a list of paths names the paths the user answers now: one with a confirmation
    or other content is answered whole (E2E-11).
    """
    new = sorted(named_paths(request.message) - set(found))
    earlier = "; ".join(
        f"{', '.join(paths)} ({question.id}): {text!r}"
        for question, text, paths in _by_question(found)
    )
    note = f"\n\nAlready answered in this run, not asked again: {earlier}."
    if new and _only_paths(request.message):
        note += f" Answer only {', '.join(new)}."
    return request.model_copy(update={"message": request.message + note})

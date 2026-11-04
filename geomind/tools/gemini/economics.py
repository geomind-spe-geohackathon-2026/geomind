"""The economics question: the case lead's rows of the cost catalogue, asked and set by code.

The case lead chooses each key's row; ``ask_economics`` writes the one question from them, and an
answer of ``approve all`` sets every value it named with ``set_case``, the currency, price year and
discount rate included, and records each row as a confirmed assumption with its citation. So no
value the user approved is dropped, and each keeps its row ``id`` and source (the run: the multi-row
keys, the currency, the price year and the discount rate were approved and never set).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.types import Request

APPROVE = "approve all"
OPTIONS = (APPROVE, "change some", "stop")
"""The options of the economics question, as the case lead's other questions have them."""
REQUIRED = ("currency", "price_year", "discount_rate")
"""The keys every economics question names, with a value or as open."""
CITED = ("row", "source", "year", "url", "status")
"""The fields of a row that go into its citation."""


class OtherRow(BaseModel):
    """Another catalogue row of a key, shown beside the recommended one."""

    model_config = ConfigDict(extra="forbid")

    row: str
    value: Any
    unit: str | None = None
    source: str | None = None


class EconomicsValue(BaseModel):
    """One economics key with the value the case lead recommends and where it comes from.

    ``key`` is the path under ``economics`` (``capex.heat_pump``, ``currency``); ``row`` the cost
    catalogue's row ``id``, none for a value no row gives; ``others`` the key's other rows.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any
    unit: str | None = None
    row: str | None = None
    source: str
    year: int | str | None = None
    url: str | None = None
    status: str | None = None
    others: list[OtherRow] = []


def _checked(values, open_keys):
    """Raise what the case lead must fix: an unknown key, a key twice, a required key not named."""
    from geomind.tools.gemini.skeleton import keys_under

    keys = [item.key.removeprefix("economics.") for item in values]
    named = keys + [key.removeprefix("economics.") for key in open_keys]
    unknown = [key for key in named if not keys_under(f"economics.{key}")]
    if unknown:
        raise ToolError(
            f"ask_economics: key = {unknown[0]!r}; expected a key of the economics, such as "
            "capex.heat_pump (describe_case(path='economics') lists them)",
            code="unknown_name",
            path="values",
        )
    twice = sorted({key for key in named if named.count(key) > 1})
    if twice:
        raise ToolError(f"ask_economics: keys = {twice}; expected each key once", path="values")
    missing = [key for key in REQUIRED if key not in named]
    if missing:
        raise ToolError(
            f"ask_economics: {', '.join(missing)} not named; expected each in values (with its "
            "row or source) or in open",
            path="values",
        )


def _amount(item):
    """Return a value with its unit as the line shows it."""
    return f"{item.value} {item.unit}" if item.unit else f"{item.value}"


def value_line(item):
    """Return the question's line of one key: path, value, row, citation and the other rows."""
    key = item.key.removeprefix("economics.")
    cited = [f"row {item.row}" if item.row else "no row"]
    cited += [str(part) for part in (item.status, item.year, item.source, item.url) if part]
    line = f"economics.{key} = {_amount(item)} | {' | '.join(cited)}"
    if item.others:
        others = "; ".join(f"{_amount(other)} [{other.row}]" for other in item.others)
        line += f" (recommended; other rows: {others})"
    return line


def question_text(values, open_keys, note=None):
    """Return the one economics question, every value on its own line, the required keys first."""
    first = sorted(values, key=lambda item: item.key not in REQUIRED)
    lines = ["Economics of the case, from the cost catalogue."]
    lines += [note] if note else []
    lines += ["", "Values (approve all sets each, with its row):"]
    lines += [value_line(item) for item in first]
    if open_keys:
        lines += ["", "Open (no usable row; give a value with change some, or leave it open):"]
        lines += [f"economics.{key.removeprefix('economics.')}" for key in open_keys]
    return "\n".join(lines)


@tool(effect="read", runs_alone=True)
def ask_economics(
    context,
    values: list[EconomicsValue],
    open: list[str] | None = None,
    note: str | None = None,
):
    """Ask the user the ONE economics question from the rows you chose, and set what they approve.

    ``values`` holds each economics key with the value you recommend: ``key`` its path under
    ``economics`` (``capex.heat_pump``, ``energy.electricity``), ``value`` and ``unit`` as the key
    takes them, ``row`` the catalogue row ``id``, ``source``, ``year``, ``url``, ``status``, and for
    a key whose rows differ ``others``, the rows you did not recommend. ``currency``,
    ``price_year`` and ``discount_rate`` are keys too: each is in ``values`` or in ``open``.
    ``open`` names the keys no usable row gives; ``note`` one line for the user. The question's
    options are approve all, change some and stop, and the user may type an answer instead. On
    approve all, every value is set in the case's economics (``set_case``) with its row in
    ``about.sources``, and each becomes a confirmed assumption with its citation; the result says
    what was set. On change some, ask which values change and to what, without options.
    """
    open_keys = list(open or [])
    _checked(values, open_keys)
    return Request(
        kind="question", message=question_text(values, open_keys, note), options=list(OPTIONS)
    )


def _nested(key, leaf):
    """Return ``{"capex": {"heat_pump": leaf}}`` for ``capex.heat_pump``."""
    patch = leaf
    for part in reversed(key.split(".")):
        patch = {part: patch}
    return patch


def _merged(target, patch):
    """Return ``target`` with ``patch`` merged in, key by key."""
    result = dict(target)
    for key, value in patch.items():
        both = isinstance(result.get(key), dict) and isinstance(value, dict)
        result[key] = _merged(result[key], value) if both else value
    return result


def citation(item):
    """Return the citation of a value: its row id and source, with what else the row gives."""
    data = item.model_dump()
    return {name: data[name] for name in CITED if data.get(name) is not None}


def approved_economics(values):
    """Return the economics merge patch of the approved values, each row kept in ``about``."""
    patch = {}
    sources = {}
    for item in values:
        key = item.key.removeprefix("economics.")
        leaf = {"value": item.value, **({"unit": item.unit} if item.unit else {})}
        patch = _merged(patch, _nested(key, leaf))
        sources[key] = citation(item)
    return {**patch, "about": {"sources": sources}}


def assumption_changes(problem, values):
    """Return the ``update_state`` operations that record each approved value as an assumption."""
    known = {item.id for item in problem.assumptions}
    changes = []
    for item in values:
        key = f"economics.{item.key.removeprefix('economics.')}"
        assumption = {
            "id": key,
            "text": f"{key} = {_amount(item)}, approved by the user",
            "value": {"value": item.value, **({"unit": item.unit} if item.unit else {})},
            "source": "agent",
            "confirmed": True,
            "reason": f"cost catalogue row {item.row}" if item.row else item.source,
            "citation": citation(item),
        }
        if key in known:
            changes.append({"op": "replace", "path": f"/assumptions/{key}", "value": assumption})
        else:
            changes.append({"op": "add", "path": "/assumptions/-", "value": assumption})
    return changes


async def economics_answered(context, tool_input, text):
    """Act on the answer to the economics question; return what the model reads.

    ``approve all`` sets every value and records the assumptions; any other answer comes back as
    it is, typed text marked so. ``answer`` keeps the user's text, which a replay acts on again.
    """
    from geomind.tools.gemini.case import set_case

    if text.strip().lower() != APPROVE:
        typed = text not in OPTIONS
        return {"answer": text, **({"typed": True} if typed else {})}
    values = [EconomicsValue.model_validate(item) for item in tool_input.get("values") or []]
    stored = await set_case.function(context, economics=approved_economics(values))
    changes = assumption_changes(context.problem, values)
    version = await context.session.change_state(changes) if changes else stored["version"]
    keys = [item.key.removeprefix("economics.") for item in values]
    return {
        "answer": text,
        "economics": "set",
        "keys": keys,
        "open": list(tool_input.get("open") or []),
        "assumptions": len(changes),
        "version": version,
    }


ask_economics.on_answer = economics_answered

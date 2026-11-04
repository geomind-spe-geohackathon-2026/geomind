"""The economics question: the case lead's rows of the cost catalogue, asked and set by code.

The case lead chooses each key's row; ``ask_economics`` writes the one question from them, and an
answer of ``approve all`` sets every value it named with ``set_case``, the currency, price year and
discount rate included, and records each row as a confirmed assumption with its citation. So no
value the user approved is dropped, and each keeps its row ``id`` and source (the run: the multi-row
keys, the currency, the price year and the discount rate were approved and never set).

The currency and the price year of values from the catalogue are the catalogue's: its
``value_2015`` in ``unit_2015`` are EUR at 2015 prices, so ``ask_economics`` sets both and never
asks for them (E2E-9). Each value's unit is checked against its key before the user is asked,
every refused one named at once, and a basis word after a row's unit is shown (E2E-10).
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
CATALOGUE_BASIS = {"currency": "EUR", "price_year": 2015}
"""The currency and price year of every value of the cost catalogue, ``knowledge/cost-sources.csv``.

Its ``value_2015`` in ``unit_2015`` are EUR at 2015 prices (Eurostat HICP, euro area, 2015 = 100),
as ``cost-sources.md`` states; a test reads both files, so the two cannot drift apart."""
BASIS_SOURCE = (
    "the cost catalogue's value_2015 and unit_2015 columns: EUR at 2015 prices "
    "(knowledge/cost-sources.md)"
)


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
    catalogue's row ``id``, none for a value no row gives; ``others`` the key's other rows. Every
    field but ``key`` takes null as left out (the run: ``others: null`` and ``source: null`` were
    21 errors and two more tries, #142); a value of null makes the key open, and a value needs its
    row or its source.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any = None
    unit: str | None = None
    row: str | None = None
    source: str | None = None
    year: int | str | None = None
    url: str | None = None
    status: str | None = None
    others: list[OtherRow] | None = None


def given_values(values, open_keys):
    """Return ``(values with a value, open keys)``: a value of null is an open key.

    A value with neither its row nor its source is refused: the user approves where it comes from.
    A key both null in ``values`` and in ``open`` is open once.
    """
    given = [item for item in values if item.value is not None]
    unsourced = [item.key for item in given if not (item.row or item.source)]
    if unsourced:
        raise ToolError(
            f"ask_economics: {unsourced[0]} has a value and no row or source; expected its "
            "catalogue row id or its source, or the key in open",
            path="values",
        )
    nulls = [item.key for item in values if item.value is None]
    return given, list(dict.fromkeys(short(key) for key in [*open_keys, *nulls]))


def short(key):
    """Return an economics key without its ``economics.`` start."""
    return key.removeprefix("economics.")


def same(given, expected):
    """Tell whether a value the model gave is the catalogue's ``expected``, as text or number."""
    if isinstance(expected, int) and not isinstance(given, bool):
        try:
            return float(given) == expected
        except (TypeError, ValueError):
            return False
    return str(given).strip() == expected


def catalogue_basis(values, open_keys):
    """Return ``(values, open keys)`` with the catalogue's currency and price year when a row is.

    A value from a catalogue row is in its ``value_2015`` and ``unit_2015``, EUR at 2015 prices
    (``CATALOGUE_BASIS``), so both are set from there with that source and taken out of ``open``;
    another value given for either is refused. Without a row, the model names both as before.
    """
    if not any(item.row for item in values):
        return values, open_keys
    for item in values:
        expected = CATALOGUE_BASIS.get(short(item.key))
        if expected is not None and not same(item.value, expected):
            raise ToolError(
                f"ask_economics: {short(item.key)} = {item.value!r}; the catalogue rows are "
                f"{BASIS_SOURCE}, so ask_economics sets currency {CATALOGUE_BASIS['currency']!r} "
                f"and price_year {CATALOGUE_BASIS['price_year']} itself: leave both out",
                path="values",
            )
    kept = [item for item in values if short(item.key) not in CATALOGUE_BASIS]
    basis = [
        EconomicsValue(key=key, value=value, source=BASIS_SOURCE)
        for key, value in CATALOGUE_BASIS.items()
    ]
    return kept + basis, [key for key in open_keys if key not in CATALOGUE_BASIS]


def fitted_units(values):
    """Return ``(values, notes)``: each value's unit as its key takes it, ``{key: note}``.

    Every value whose unit its key refuses is named in one error with the units the key takes, so
    the user is asked only what approve all can set (E2E-10: ``EUR/MWh cold`` on ice storage was
    refused after the user's approve all, and the answer was lost).
    """
    from geomind.tools.gemini.unit_bridge import economics_unit

    fitted, notes, refused = [], {}, []
    for item in values:
        unit, note, accepted = economics_unit(item.key, item.unit)
        if unit is None and item.unit is not None and accepted:
            refused.append(f"{short(item.key)}: unit {item.unit!r}; expected {', '.join(accepted)}")
            continue
        if note:
            notes[short(item.key)] = note
        fitted.append(item.model_copy(update={"unit": unit}))
    if refused:
        count = f"{len(refused)} values have" if len(refused) > 1 else "1 value has"
        raise ToolError(
            f"ask_economics: {count} a unit the key does not take; fix each (a row whose unit "
            "its key refuses is not usable: leave it out, or the key in open): "
            + "; ".join(refused),
            code="invalid_unit",
            path="values",
        )
    return fitted, notes


def prepared(values, open_keys):
    """Return ``(values, open keys, notes)`` of the question, or raise what the model must fix."""
    values, open_keys = given_values(values, open_keys)
    values, open_keys = catalogue_basis(values, open_keys)
    values, notes = fitted_units(values)
    _checked(values, open_keys)
    return values, open_keys, notes


def _checked(values, open_keys):
    """Raise what the case lead must fix: an unknown key, a key twice, a required key not named."""
    from geomind.tools.gemini.skeleton import keys_under

    keys = [short(item.key) for item in values]
    named = keys + list(open_keys)
    unknown = [key for key in named if not keys_under(f"economics.{key}")]
    if unknown:
        raise ToolError(
            f"ask_economics: key = {unknown[0]!r}; expected a key of the economics, such as "
            "capex.heat_pump (describe_case(path='economics') lists them)",
            code="unknown_name",
            path="values",
        )
    both = [key for key in dict.fromkeys(keys) if key in open_keys]
    if both:
        raise ToolError(
            f"ask_economics: {', '.join(both)} is in values and in open; expected each key in "
            "one: in values with its value and row, or in open (value null) when no usable row "
            "gives it",
            path="values",
        )
    twice = sorted({key for key in keys if keys.count(key) > 1})
    if twice:
        raise ToolError(
            f"ask_economics: keys = {twice}; expected each key once in values: one recommended "
            "row, the key's other rows in its others",
            path="values",
        )
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


def value_line(item, note=None):
    """Return the question's line of one key: path, value, row, citation and the other rows.

    ``note`` says the basis of the row's unit beside the key's (``fitted_units``).
    """
    key = item.key.removeprefix("economics.")
    cited = [f"row {item.row}" if item.row else "no row"]
    cited += [str(part) for part in (item.status, item.year, item.source, item.url) if part]
    cited += [note] if note else []
    line = f"economics.{key} = {_amount(item)} | {' | '.join(cited)}"
    if item.others:
        others = "; ".join(f"{_amount(other)} [{other.row}]" for other in item.others)
        line += f" (recommended; other rows: {others})"
    return line


def question_text(values, open_keys, note=None, notes=None):
    """Return the one economics question, every value on its own line, the required keys first."""
    first = sorted(values, key=lambda item: short(item.key) not in REQUIRED)
    lines = ["Economics of the case, from the cost catalogue."]
    lines += [note] if note else []
    lines += ["", "Values (approve all sets each, with its row):"]
    lines += [value_line(item, (notes or {}).get(short(item.key))) for item in first]
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
    a key whose rows differ ``others``, the rows you did not recommend. ``discount_rate`` is a
    key too, in ``values`` or in ``open``. A value from a catalogue row is its ``value_2015`` in
    ``unit_2015``, EUR at 2015 prices, so this tool sets ``currency`` EUR and ``price_year`` 2015
    itself: leave both out (without any row, name each in ``values`` or ``open``). A row's unit
    goes as the row writes it (``EUR/W electric``); a unit its key does not take is refused,
    every one at once, before the user is asked. ``open`` names the keys no usable row gives, each
    key once in ``values`` or ``open``; ``note`` one line for the user. A field with
    nothing to say is null or left out; a key whose value is null is open. The question's
    options are approve all, change some and stop, and the user may type an answer instead. On
    approve all, every value is set in the case's economics (``set_case``) with its row in
    ``about.sources``, and each becomes a confirmed assumption with its citation; the result says
    what was set. On change some, ask which values change and to what, without options.
    """
    values, open_keys, notes = prepared(values, list(open or []))
    message = question_text(values, open_keys, note, notes)
    return Request(kind="question", message=message, options=list(OPTIONS))


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


def citation(item, note=None):
    """Return the citation of a value: its row id and source, with what else the row gives.

    ``note`` is the basis of the row's unit (``fitted_units``), kept as ``basis``.
    """
    data = item.model_dump()
    cited = {name: data[name] for name in CITED if data.get(name) is not None}
    return {**cited, "basis": note} if note else cited


def approved_economics(values, notes=None):
    """Return the economics merge patch of the approved values, each row kept in ``about``."""
    patch = {}
    sources = {}
    for item in values:
        key = item.key.removeprefix("economics.")
        leaf = {"value": item.value, **({"unit": item.unit} if item.unit else {})}
        patch = _merged(patch, _nested(key, leaf))
        sources[key] = citation(item, (notes or {}).get(key))
    return {**patch, "about": {"sources": sources}}


def assumption_changes(problem, values, notes=None):
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
            "citation": citation(item, (notes or {}).get(short(item.key))),
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
    values, open_keys, notes = prepared(values, list(tool_input.get("open") or []))
    stored = await set_case.function(context, economics=approved_economics(values, notes))
    changes = assumption_changes(context.problem, values, notes)
    version = await context.session.change_state(changes) if changes else stored["version"]
    keys = [item.key.removeprefix("economics.") for item in values]
    return {
        "answer": text,
        "economics": "set",
        "keys": keys,
        "open": open_keys,
        "assumptions": len(changes),
        "version": version,
    }


ask_economics.on_answer = economics_answered

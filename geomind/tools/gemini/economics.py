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

import functools
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from geomind.errors import ToolError
from geomind.context.skills import tool_section
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
"""The currency and price year of every value of the cost catalogue, ``knowledge/data-economics.csv``.

Its ``value_2015`` in ``unit_2015`` are EUR at 2015 prices (Eurostat HICP, euro area, 2015 = 100),
as ``data-economics.md`` states; a test reads both files, so the two cannot drift apart."""
BASIS_SOURCE = (
    "the cost catalogue's value_2015 and unit_2015 columns: EUR at 2015 prices "
    "(knowledge/data-economics.md)"
)


ROW = "the catalogue row's id, as text (the row's id field, not the row)"
"""What ``row`` holds, as the tool's schema says it (E2E-14: the row object was sent)."""


def row_by_id(data):
    """Return ``(input, refusal)``: ``row`` as the row's id when the model sent the row object.

    The object's citation fields fill those the input leaves out, so nothing the model gave is
    dropped; an object without its ``id`` gives the refusal that says what ``row`` holds.
    """
    if not isinstance(data, dict) or not isinstance(data.get("row"), dict):
        return data, None
    row = data["row"]
    if not isinstance(row.get("id"), str):
        return data, f"row is an object without its id; expected {ROW}"
    cited = {key: row[key] for key in CITED[1:] if row.get(key) is not None}
    given = {key: value for key, value in data.items() if value is not None}
    return {**cited, **given, "row": row["id"]}, None


class OtherRow(BaseModel):
    """Another catalogue row of a key, shown beside the recommended one."""

    model_config = ConfigDict(extra="forbid")

    row: str = Field(description=ROW)
    value: Any = None
    unit: str | None = None
    source: str | None = None
    year: int | str | None = None
    url: str | None = None
    status: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _row_by_id(cls, data):
        """Take a bare row id, and read a row object by its ``id`` (``row_by_id``)."""
        if isinstance(data, str):
            return {"row": data}
        read, refusal = row_by_id(data)
        if refusal:
            raise ValueError(refusal)
        return read


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
    row: str | None = Field(default=None, description=ROW)
    source: str | None = None
    year: int | str | None = None
    url: str | None = None
    status: str | None = None
    others: list[OtherRow] | None = None
    uncertainty: dict[str, Any] | None = Field(
        default=None,
        description=(
            "the value's uncertainty as the case writes it, e.g. {kind: normal, std, min, max}, "
            "from the source that gives it; set with the value on approve all (QA-216)"
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _row_by_id(cls, data):
        """Read a row object by its ``id`` (``row_by_id``)."""
        read, refusal = row_by_id(data)
        if refusal:
            raise ValueError(refusal)
        return read


CATALOGUE = "knowledge/data-economics.csv"
"""The cost catalogue in the knowledge base, where ``ask_economics`` reads each row it is named."""


def catalogue_rows(context):
    """Return ``{id: row}`` of the cost catalogue, or ``None`` for a run without it.

    A run whose knowledge base lacks the catalogue keeps the fields the input gives.
    """
    import csv
    import io

    from geomind.tools.knowledge import has_knowledge, knowledge_file

    session = getattr(context, "session", None)
    workspace = getattr(session, "workspace", None)
    if not has_knowledge(workspace) or not workspace.knowledge_files():
        return None
    try:
        content = knowledge_file(context, "ask_economics", CATALOGUE)
    except ToolError:
        return None
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else str(content)
    return {row["id"]: row for row in csv.DictReader(io.StringIO(text)) if row.get("id")}


def _number(text):
    """Return a catalogue cell as a number when it is one, else the text."""
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    return int(number) if number.is_integer() and "." not in str(text) else number


def _row_fields(rows, key, row_id):
    """Return the value, unit and citation of catalogue row ``row_id`` for ``key``, or raise."""
    row = rows.get(row_id)
    if row is None:
        near = [item for item, data in rows.items() if data.get("path") == f"economics.{key}"]
        raise ToolError(
            f"ask_economics: row = {row_id!r} is not in {CATALOGUE}; expected the id of a row "
            f"of economics.{key}"
            + (f": {', '.join(near)}" if near else ", or the key in open")
            + "; a value a Knowledge document or a project file gives goes as {key, value, unit, "
            "source} with no row, never with a row id you made up",
            code="unknown_name",
            path="values",
        )
    if row.get("path") and row["path"] != f"economics.{key}":
        raise ToolError(
            f"ask_economics: row {row_id} is for {row['path']}, not economics.{key}; expected a "
            "row whose path is the key",
            path="values",
        )
    if not (row.get("value_2015") or "").strip():
        raise ToolError(
            f"ask_economics: row {row_id} has no value ({row.get('status') or 'no status'}); "
            f"expected another row of economics.{key}, or the key in open",
            path="values",
        )
    fields = {
        "value": _number(row["value_2015"]),
        "unit": (row.get("unit_2015") or "").strip() or None,
        "source": row.get("source") or None,
        "year": _number(row["year"]) if row.get("year") else None,
        "url": row.get("url") or None,
        "status": row.get("status") or None,
    }
    return {name: value for name, value in fields.items() if value is not None}


def has_value(rows, row_id):
    """Tell whether catalogue row ``row_id`` exists and has a 2015 value (QA-045)."""
    row = rows.get(row_id)
    return row is None or bool((row.get("value_2015") or "").strip())


def usable_rows(rows, item, skipped):
    """Return ``item`` without its rows that have no 2015 value, each named in ``skipped``.

    A recommended row with no value gives way to the first usable one of its ``others``; with
    none left, the key is open (value null). An unknown row is left for ``_row_fields`` to refuse.
    """
    others = list(item.others or ())
    dropped = [other.row for other in others if not has_value(rows, other.row)]
    others = [other for other in others if has_value(rows, other.row)]
    update = {"others": others} if item.others is not None else {}
    if item.row and not has_value(rows, item.row):
        dropped.insert(0, item.row)
        if others:
            update.update(row=others[0].row, others=others[1:])
        else:
            update.update(row=None, value=None, others=None)
    skipped += [f"{short(item.key)}: row {row} (no 2015 value)" for row in dropped]
    return item.model_copy(update=update) if update else item


def skipped_note(skipped):
    """Return the line that names the catalogue rows left out for having no 2015 value, or None."""
    if not skipped:
        return None
    return "Left out, catalogue rows with no 2015 value: " + "; ".join(skipped)


STATUS_RANK = {"verified": 0, "secondary": 1}
"""The order of sourced rows; a ``placeholder`` row has no source and is never recommended."""
BOUND_WORDS = ("upper bound", "proxy")
"""Words of a row's note or id that keep it from being recommended over a usable row."""
REFERENCE_ONLY = ("erratum", "waste-density")
"""Words of a row id kept for reference only: never a value nor in ``others``."""
NOT_REAL_RATE = ("social", "nominal")
"""Words of a ``discount_rate`` row that is not a real financial rate (the catalogue is real)."""


def _usable(key, row):
    """Tell whether a catalogue row can be a value of ``key``: a 2015 value in a unit it takes."""
    from geomind.tools.gemini.unit_bridge import economics_unit

    if not (row.get("value_2015") or "").strip():
        return False
    given = (row.get("unit_2015") or "").strip() or None
    unit, _, accepted = economics_unit(key, given)
    return not (unit is None and given is not None and accepted)


def _rank(row):
    """Return the sort key of a row: sourced first, verified first, no bound or proxy, latest.

    A ``discount_rate`` row of a social or nominal rate comes after a real financial one, as the
    catalogue's prices are real (EUR at 2015 prices).
    """
    text = f"{row.get('id', '')} {row.get('note', '')}".lower()
    year = _number(row["year"]) if (row.get("year") or "").strip() else 0
    rate = row.get("path") == "economics.discount_rate"
    return (
        rate and any(word in row.get("id", "") for word in NOT_REAL_RATE),
        STATUS_RANK.get(row.get("status"), 9),
        any(word in text for word in BOUND_WORDS),
        -(year if isinstance(year, (int, float)) else 0),
    )


POLICY_KEYS = ("revenue.subsidy",)
"""Keys of a policy the site may not have (a subsidy scheme): never filled with a recommended
row; open unless the case lead names them because the user or the brief gives a subsidy (QA-084:
a Dutch SDE++ amount and duration went into a case whose user said no subsidy)."""


def recommended(context, values, open_keys):
    """Return ``(values, open keys)`` with every catalogue key the case lead did not name (QA-013).

    The case lead names only exceptions (another row, a key open, a value from a server or the
    user); each other economics key of the catalogue goes in with its recommended row, by the
    case lead's rule: a sourced row over a placeholder, verified over secondary, a row whose note
    calls it an upper bound or a proxy last, then the latest year; its other sourced rows in
    ``others``. A key with only placeholder rows is open. Without the catalogue nothing is added.
    """
    rows = catalogue_rows(context)
    if rows is None:
        return values, open_keys
    named = {short(item.key) for item in values} | {short(key) for key in open_keys}
    by_key = {}
    for row in rows.values():
        key = short(row.get("path") or "")
        if row.get("path", "").startswith("economics.") and key not in named and is_economics(key):
            by_key.setdefault(key, []).append(row)
    added, opened = [], []
    for key, found in sorted(by_key.items()):
        if key in CATALOGUE_BASIS:
            continue
        if key.startswith(POLICY_KEYS):
            opened.append(key)
            continue
        sourced = sorted(
            (
                row
                for row in found
                if row.get("status") in STATUS_RANK
                and _usable(key, row)
                and not any(word in row.get("id", "") for word in REFERENCE_ONLY)
            ),
            key=_rank,
        )
        if not sourced:
            opened.append(key)
            continue
        others = [{"row": row["id"]} for row in sourced[1:]]
        item = {"key": key, "row": sourced[0]["id"], **({"others": others} if others else {})}
        added.append(EconomicsValue.model_validate(item))
    return [*values, *added], [*open_keys, *opened]


def from_catalogue(context, values, skipped=None):
    """Return ``values`` with every named row's value, unit and citation read from the catalogue.

    The case lead names a key and its row ids; the numbers come from the knowledge base, never
    from what the model typed (run 86ddac2a: typing every row's value, unit, source and url of
    about 40 keys ran past the 16,000-token output limit three times and the case had no
    economics). A run without the catalogue keeps the fields the input gives.
    """
    rows = catalogue_rows(context)
    if rows is None:
        return values
    skipped = [] if skipped is None else skipped
    read = []
    for item in values:
        key = short(item.key)
        if not is_economics(key):
            read.append(item)
            continue
        item = usable_rows(rows, item, skipped)
        update = _row_fields(rows, key, item.row) if item.row else {}
        others = [
            other.model_copy(update=_row_fields(rows, key, other.row))
            for other in item.others or ()
        ]
        if item.others is not None:
            update["others"] = others
        read.append(item.model_copy(update=update))
    return read


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


@functools.lru_cache(maxsize=512)
def is_economics(key):
    """Tell whether ``key`` (with or without ``economics.``) is a key of the case's economics."""
    from geomind.tools.gemini.skeleton import keys_under

    return bool(keys_under(f"economics.{short(key)}"))


def not_economics(values, open_keys):
    """Return ``(values, open keys, dropped)`` without the keys that are not economics keys.

    A case value put in the question (``utilities.electricity.co2_intensity``) is left out with a
    note instead of refusing the whole question, which the case lead retried again and again
    (QA-007); it is set with ``set_case`` at its own path.
    """
    dropped = [short(item.key) for item in values if not is_economics(item.key)]
    dropped += [short(key) for key in open_keys if not is_economics(key)]
    kept = [item for item in values if is_economics(item.key)]
    return kept, [key for key in open_keys if is_economics(key)], list(dict.fromkeys(dropped))


def dropped_note(dropped):
    """Return the line that names the keys left out as not economics keys, or None."""
    if not dropped:
        return None
    return (
        f"Left out, not economics keys (set each with set_case at its own path): "
        f"{', '.join(dropped)}"
    )


PER_ENERGY = "opex.per_energy."


def whole_per_energy(values, open_keys):
    """Return ``(values, open keys, moved keys)`` with the per-energy map all given or all open.

    Once one ``opex.per_energy`` price is set, gemini needs one for every producing kind the
    plant uses, so a map with a kind left open (the chillers, which no row prices) gave no cost
    metric at all (QA-105). With any kind open, every kind goes to ``open``: no map, and the
    plant is costed without per-energy O&M.
    """
    if not any(short(key).startswith(PER_ENERGY) for key in open_keys):
        return values, open_keys, []
    moved = [short(item.key) for item in values if short(item.key).startswith(PER_ENERGY)]
    kept = [item for item in values if not short(item.key).startswith(PER_ENERGY)]
    return kept, list(dict.fromkeys([*open_keys, *moved])), moved


def per_energy_note(moved):
    """Return the line of the question that says why the per-energy prices are all open."""
    return (
        f"Open as a whole: {', '.join(moved)}. A per-energy map needs a price for every kind "
        "the plant runs, and the chillers have none, so no map is set; give every kind's price "
        "with change some to set one."
    )


FRACTION_WORDS = ("rate", "share", "fraction")
"""Words of an economics key that is a fraction with no unit: 0.08, never 8, for 8 %."""


def refuse_percents(values):
    """Raise for a fraction key given a number above 1 with no unit (QA-120: "8 %" sent as 8).

    The key takes no unit, so 8 would be 800 %; converting is gemini's, so the model is told
    the form instead: 0.08.
    """
    for item in values:
        leaf = short(item.key).rsplit(".", 1)[-1]
        number = item.value if isinstance(item.value, (int, float)) else None
        if item.row or number is None or isinstance(number, bool):
            continue
        if any(word in leaf for word in FRACTION_WORDS) and number > 1 and not item.unit:
            raise ToolError(
                f"ask_economics: {short(item.key)} = {number} with no unit; the key is a fraction "
                f"with no unit, so {number} reads as {number * 100:g} %. For {number:g} % give "
                f"{number / 100:g}",
                code="invalid_value",
                path="values",
                suggestions=[f'{{"key": "{short(item.key)}", "value": {number / 100:g}}}'],
            )


def prepared(values, open_keys, dropped=None):
    """Return ``(values, open keys, notes)`` of the question, or raise what the model must fix.

    ``dropped``, a list, gets the keys left out as not economics keys (``not_economics``).
    """
    values, open_keys = given_values(values, open_keys)
    values, open_keys, _ = whole_per_energy(values, open_keys)
    values, open_keys, left_out = not_economics(values, open_keys)
    if dropped is not None:
        dropped += left_out
    values, open_keys = catalogue_basis(values, open_keys)
    refuse_percents(values)
    values, notes = fitted_units(values)
    values, open_keys = mismatched_open(values, open_keys, notes)
    _checked(values, open_keys)
    return values, open_keys, notes


MISMATCH = "not converted, the user decides"
"""The end of a ``fitted_units`` note of a row on another power basis than its key."""


def mismatched_open(values, open_keys, notes):
    """Return ``(values, open keys)`` with each row on another basis than its key moved to open.

    QA-192: approve all set a circulation pump's EUR/W heat as EUR/W shaft; such a row is no value
    to approve: the key goes to Open with its note, for the user to give a value.
    """
    moved = [item for item in values if MISMATCH in (notes.get(short(item.key)) or "")]
    if not moved:
        return values, open_keys
    keys = [short(item.key) for item in moved]
    kept = [item for item in values if short(item.key) not in keys]
    return kept, list(open_keys) + [key for key in keys if key not in open_keys]


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


COUNTRIES = {
    "nl": "the Netherlands", "se": "Sweden", "no": "Norway", "dk": "Denmark", "de": "Germany",
    "fr": "France", "uk": "the United Kingdom", "be": "Belgium", "fi": "Finland", "is": "Iceland",
    "it": "Italy", "es": "Spain", "ch": "Switzerland", "at": "Austria", "pl": "Poland",
}
"""The country codes a catalogue row id names its country with (``electricity-nl-eurostat-...``)."""
NATIONAL_SCHEMES = {"sde": "the Netherlands"}
"""Words of a row id that name one country's scheme (SDE++ is Dutch)."""


def row_region(row_id):
    """Return the country a catalogue row's prices are of, or ``None`` for a general row (QA-085).

    A band name after ``band`` (``band-id``, ``band-ie``) is a consumer band, not a country.
    """
    tokens = (row_id or "").lower().split("-")
    for index, token in enumerate(tokens):
        if index and tokens[index - 1] == "band":
            continue
        if token in NATIONAL_SCHEMES:
            return NATIONAL_SCHEMES[token]
        if token in COUNTRIES:
            return COUNTRIES[token]
    return None


def value_line(item, note=None):
    """Return the question's line of one key: path, value, row, citation and the other rows.

    ``note`` says the basis of the row's unit beside the key's (``fitted_units``).
    """
    key = item.key.removeprefix("economics.")
    cited = [f"row {item.row}" if item.row else "no row"]
    cited += [str(part) for part in (item.status, item.year, item.source, item.url) if part]
    cited += [note] if note else []
    region = row_region(item.row)
    cited += [f"prices of {region}"] if region else []
    line = f"economics.{key} = {_amount(item)} | {' | '.join(cited)}"
    if item.others:
        others = "; ".join(
            f"{_amount(other)} [{', '.join(part for part in (other.row, other.status) if part)}]"
            for other in item.others
        )
        line += f" (recommended; other rows: {others})"
    return line


def open_line(key, note=None):
    """Return the line of an open key, with the note of a row left out for its basis."""
    line = f"economics.{key.removeprefix('economics.')}"
    return f"{line} ({note})" if note else line


def question_text(values, open_keys, note=None, notes=None):
    """Return the one economics question, every value on its own line, the required keys first."""
    first = sorted(values, key=lambda item: short(item.key) not in REQUIRED)
    lines = ["Economics of the case, from the cost catalogue."]
    lines += [note] if note else []
    lines += ["", "Values (approve all sets each, with its row):"]
    lines += [value_line(item, (notes or {}).get(short(item.key))) for item in first]
    regions = sorted({row_region(item.row) for item in first} - {None})
    if regions:
        lines += [
            "",
            f"Rows marked 'prices of ...' are prices of {', '.join(regions)}: they fit only a site "
            "there. Approve them as an assumption, or name the site's country to take its rows.",
        ]
    if open_keys:
        lines += ["", "Open (no usable row; give a value with change some, or leave it open):"]
        lines += [open_line(key, (notes or {}).get(short(key))) for key in open_keys]
    return "\n".join(lines)


@tool(effect="read", runs_alone=True)
def ask_economics(
    context,
    values: list[EconomicsValue],
    open: list[str] | None = None,
    note: str | None = None,
):
    """Ask the user the ONE economics question from the rows you chose, and set what they approve.

    Skill `setting-the-case`.
    """
    dropped, skipped = [], []
    values, open_keys = recommended(context, list(values), list(open or []))
    values = from_catalogue(context, values, skipped)
    _, _, moved = whole_per_energy(*given_values(values, list(open_keys)))
    values, open_keys, notes = prepared(values, open_keys, dropped)
    message = question_text(values, open_keys, note, notes)
    if moved:
        message += "\n\n" + per_energy_note(moved)
    if dropped:
        message += "\n\n" + dropped_note(dropped)
    if skipped:
        message += "\n\n" + skipped_note(skipped)
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
        leaf = {**leaf, **({"uncertainty": item.uncertainty} if item.uncertainty else {})}
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


HOLDS_BACK = ("except", "but", "without", "apart from", "other than", "not ")
"""Words after a typed "approve all" that keep part back: then it is a change, not approve all."""
TYPED_NOTE = (
    "nothing was set: the user typed an answer. Act on it: for values to change, call "
    "ask_economics again with those rows changed; never ask the same question unchanged"
)


def approves_all(text):
    """Tell whether an answer approves every value: the option, or typed text that starts so.

    A typed "Approve all as recommended, ..." is approve all (QA-079: it set nothing and the same
    question came again); "approve all except ..." keeps part back and is a change. Only the first
    sentence is read for that; the rest goes to the agent as ``user_note``.
    """
    words = " ".join(text.strip().lower().split())
    if words == APPROVE:
        return True
    if not words.startswith(APPROVE):
        return False
    rest = words[len(APPROVE):].split(". ")[0]
    return not any(word in f"{rest} " for word in HOLDS_BACK)


async def economics_answered(context, tool_input, text):
    """Act on the answer to the economics question; return what the model reads.

    ``approve all`` sets every value and records the assumptions; any other answer comes back as
    it is, typed text marked so. ``answer`` keeps the user's text, which a replay acts on again.
    """
    from geomind.tools.gemini.case import set_case

    approves = approves_all(text)
    if not approves:
        typed = text not in OPTIONS
        note = {"note": TYPED_NOTE} if typed else {}
        return {"answer": text, "economics": "not set", **({"typed": True} if typed else {}), **note}
    values = [EconomicsValue.model_validate(item) for item in tool_input.get("values") or []]
    values, open_keys = recommended(context, values, list(tool_input.get("open") or []))
    values = from_catalogue(context, values)
    dropped = []
    values, open_keys, notes = prepared(values, open_keys, dropped)
    stored = await set_case.function(context, economics=approved_economics(values, notes))
    changes = assumption_changes(context.problem, values, notes)
    version = await context.session.change_state(changes) if changes else stored["version"]
    keys = [item.key.removeprefix("economics.") for item in values]
    extra = text.strip() if text.strip().lower() != APPROVE else ""
    return {
        "answer": text,
        **({"user_note": extra} if extra else {}),
        "economics": "set",
        "keys": keys,
        "open": open_keys,
        "assumptions": len(changes),
        "version": version,
        **({"not_set": dropped, "note": dropped_note(dropped)} if dropped else {}),
    }


ask_economics.on_answer = economics_answered
ask_economics.description = f"{ask_economics.description}\n\n{tool_section('ask_economics')}"

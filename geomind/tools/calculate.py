"""The tool that derives a value from sourced values, with gemini doing every unit conversion.

Each operand is a reference to a value that has a source (a case field, a catalogue row, a
user-approved assumption, a stored result, an earlier calculation), a named constant (pi, e) or a
plain number shown as plain; every calculation has one sourced operand at least (Sahand,
2026-11-05). The
result is kept in the problem state as a ``Calculation`` with the source of every operand, so a
later tool or the report cites it by id.

NOTE: gemini gives each unit's SI unit and its scale and offset (``gm.units.si_unit``,
``gm.units.si_conversion``); geomind only combines the SI units' dimensions (W is kg m2 s-3), a
fact about the units, never a factor. A ``yr`` in an SI unit (``J/yr``) is turned into seconds
with gemini's own scale of ``yr``.
"""

import math
import re
from uuid import uuid4
from typing import Any, Literal

from geomind.context.skills import skill_hint
from geomind.errors import ToolError
from geomind.tools.base import tool

OPERATIONS = ("add", "subtract", "multiply", "divide", "power", "min", "max", "sum", "mean")
SAME_DIMENSION = ("add", "subtract", "min", "max", "sum", "mean")
SOURCED_KINDS = ("case", "assumption", "catalogue", "stored", "calculation")
"""Operands with a source; every calculation needs one at least."""
REFERENCE_KINDS = (*SOURCED_KINDS, "constant", "number")
CONSTANTS = {"pi": (math.pi, "-"), "e": (math.e, "-"), "g": (9.80665, "m/s2")}
"""Named constants an operand may be, ``(value, unit)``: pi, e and the standard gravity ``g``
(9.80665 m/s2, the CGPM's defined value); they are not sourced (QA-074: rho * g * h)."""
DERIVED = {
    "W": {"kg": 1, "m": 2, "s": -3},
    "J": {"kg": 1, "m": 2, "s": -2},
    "Pa": {"kg": 1, "m": -1, "s": -2},
    "Hz": {"s": -1},
}
"""SI units gemini's table uses that are made of others: dimensions, never factors."""
DIMENSIONLESS = ("-", "1", "")
HINT = skill_hint("calculator")
_TOKEN = re.compile(r"\s*(\(|\)|/|\.|\^-?[0-9.]+|[A-Za-z]+[0-9]*|1)")


def _error(message, path=None, code="invalid_input"):
    """Return a ``ToolError`` of ``calculate`` that points at its skill."""
    return ToolError(f"calculate: {message}; {HINT}", code=code, path=path)


def _merge(total, part, power):
    """Add the exponents of ``part`` times ``power`` into ``total``."""
    for name, exponent in part.items():
        total[name] = total.get(name, 0) + exponent * power
        if abs(total[name]) < 1e-12:
            del total[name]


def _symbol(text):
    """Return ``(dimensions, scale)`` of one SI symbol such as ``m3``, ``J`` or ``yr``."""
    import gemini as gm

    name, digits = re.fullmatch(r"([A-Za-z]+)([0-9]*)", text).groups()
    power = int(digits) if digits else 1
    if name == "yr":
        scale, _ = gm.units.si_conversion("yr")
        return {"s": power}, scale**power
    if name == "rad":
        return {}, 1.0
    base = DERIVED.get(name, {name: 1})
    return {key: value * power for key, value in base.items()}, 1.0


def dimensions(si):
    """Return ``(dimensions, scale)`` of an SI unit of gemini such as ``currency/(W/K)``.

    ``scale`` turns a value in that SI unit into base units: one for all but a unit with ``yr``.
    """
    if si in DIMENSIONLESS:
        return {}, 1.0
    tokens = _TOKEN.findall(si)
    if "".join(tokens) != si.replace(" ", ""):
        raise _error(f"unit = {si!r}; expected an SI unit of gemini")
    position = 0

    def factor():
        nonlocal position
        token = tokens[position]
        position += 1
        if token == "(":
            found = product()
            position += 1
        elif token == "1":
            found = ({}, 1.0)
        else:
            found = _symbol(token)
        if position < len(tokens) and tokens[position].startswith("^"):
            power = float(tokens[position][1:])
            position += 1
            found = ({key: value * power for key, value in found[0].items()}, found[1] ** power)
        return found

    def product():
        nonlocal position
        total, scale = factor()
        total = dict(total)
        while position < len(tokens) and tokens[position] in ("/", "."):
            sign = -1 if tokens[position] == "/" else 1
            position += 1
            part, part_scale = factor()
            _merge(total, part, sign)
            scale *= part_scale**sign
        return total, scale

    return product()


def _unit_dimensions(unit, path):
    """Return ``(dimensions, base scale, gemini scale, offset)`` of a unit gemini knows."""
    import gemini as gm

    si = gm.units.si_unit(unit)
    if si is None:
        import difflib

        known = [member.value for member in gm.units.Unit]
        near = difflib.get_close_matches(unit, known, n=5, cutoff=0.5)
        hint = f"; the nearest it knows: {', '.join(near)}" if near else ""
        raise _error(f"unit = {unit!r} is not a unit gemini knows{hint}", path, "invalid_unit")
    found, scale = dimensions(si)
    gemini_scale, offset = gm.units.si_conversion(unit)
    return found, scale, gemini_scale, offset


def units_of(found):
    """Return the units gemini knows whose dimensions are ``found``, for an error to list."""
    import gemini as gm

    names = []
    for member in gm.units.Unit:
        try:
            if dimensions(gm.units.si_unit(member.value))[0] == found:
                names.append(member.value)
        except ToolError:
            continue
    return names


def _described(found):
    """Return dimensions as text, such as ``kg m2 s-3``, or ``dimensionless``."""
    if not found:
        return "dimensionless"
    return " ".join(f"{name}{'' if power == 1 else f'{power:g}'}" for name, power in found.items())


def _quantity(value, path, where):
    """Return ``(value, unit)`` of a stored number or ``{"value", "unit"}``; anything else raises."""
    if isinstance(value, bool):
        raise _error(f"{where} is a true/false value, not a number", path)
    if isinstance(value, (int, float)):
        return float(value), "-"
    if isinstance(value, dict) and isinstance(value.get("value"), (int, float)):
        unit = value.get("unit")
        return float(value["value"]), unit if isinstance(unit, str) and unit else "-"
    raise _error(f"{where} is {type(value).__name__}, not one number with its unit", path)


def _walk(value, dotted, path, where):
    """Return the part of ``value`` at a dotted (or ``/``) path of keys and list indexes."""
    from geomind.tools.stored import path_keys

    walked = []
    for part in path_keys(value, dotted.replace("/", ".").strip(".")):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.lstrip("-").isdigit() and abs(int(part)) < len(value):
            value = value[int(part)]
        else:
            names = list(value)[:20] if isinstance(value, dict) else []
            raise _error(
                f"{where}: {'.'.join([*walked, part])} does not exist"
                + (f"; expected one of {', '.join(map(str, names))}" if names else ""),
                path,
                "unknown_name",
            )
        walked.append(part)
    return value


def _case(context, reference, path):
    """Return the operand of a case field path."""
    case = context.problem.case
    if case is None:
        raise _error("the case is not set yet; set_case first", path)
    value, unit = _quantity(_walk(case, reference["case"], path, "case"), path, "the case field")
    return value, unit, {"kind": "case", "path": reference["case"]}


def _assumption(context, reference, path):
    """Return the operand of a user-confirmed assumption."""
    ids = {item.id: item for item in context.problem.assumptions}
    item = ids.get(reference["assumption"])
    if item is None:
        known = ", ".join(ids) or "none"
        raise _error(f"assumption {reference['assumption']!r} is not in the state ({known})", path)
    if not item.confirmed:
        raise _error(
            f"assumption {item.id} is not confirmed; ask the user to approve it with its source",
            path,
        )
    value, unit = _quantity(item.value, path, f"assumption {item.id}")
    source = {"kind": "assumption", "id": item.id, "text": item.text, "source": item.source}
    return value, unit, {**source, **({"citation": item.citation} if item.citation else {})}


def _catalogue(context, reference, path):
    """Return the operand of a cost catalogue row, its 2015 value and unit with its citation."""
    from geomind.tools.gemini.economics import CATALOGUE, catalogue_rows

    rows = catalogue_rows(context)
    if rows is None:
        raise _error(f"this run has no {CATALOGUE} in its knowledge base", path)
    row = rows.get(reference["catalogue"])
    if row is None:
        raise _error(f"row {reference['catalogue']!r} is not in {CATALOGUE}", path, "unknown_name")
    text = (row.get("value_2015") or "").strip()
    if not text:
        raise _error(f"row {reference['catalogue']} has no 2015 value", path)
    unit, _, basis = (row.get("unit_2015") or "-").strip().partition(" ")
    keys = ("item", "source", "publisher", "year", "page", "url", "status", "price_year")
    source = {"kind": "catalogue", "row": reference["catalogue"], "document": CATALOGUE}
    source |= {key: row[key] for key in keys if row.get(key)}
    if basis:
        source["basis"] = basis
    return float(text), unit or "-", source


def _stored(context, reference, path):
    """Return the operand of one value in a result stored by reference."""
    stored = context.session.load_artifact(reference["stored"])
    if stored is None:
        raise _error(f"stored = {reference['stored']!r} is not a stored result", path)
    part = reference.get("path")
    if not isinstance(part, str) or not part:
        raise _error("a stored operand needs path, the dotted path of one value in it", path)
    value, unit = _quantity(_walk(stored, part, path, reference["stored"]), path, "the stored part")
    return value, unit, {"kind": "stored", "reference": reference["stored"], "path": part}


def _calculation(context, reference, path):
    """Return the operand of an earlier calculation."""
    ids = {item.id: item for item in context.problem.calculations}
    item = ids.get(reference["calculation"])
    if item is None:
        known = ", ".join(ids) or "none"
        raise _error(f"calculation {reference['calculation']!r} does not exist ({known})", path)
    source = {"kind": "calculation", "id": item.id, "label": item.label}
    return float(item.value), item.unit, {**source, "expression": item.expression}


def _constant(context, reference, path):
    """Return the operand of a named mathematical constant."""
    name = reference["constant"]
    if name not in CONSTANTS:
        raise _error(f"constant = {name!r}; expected one of {', '.join(CONSTANTS)}", path)
    value, unit = CONSTANTS[name]
    return value, unit, {"kind": "constant", "name": name}


def _number(context, reference, path):
    """Return the operand of a plain number the agent gives, shown as plain in the expression."""
    value, unit = reference["number"], reference.get("unit", "-")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _error(f"number = {value!r}; expected a finite number", path)
    if not isinstance(unit, str) or not unit:
        raise _error(f"unit = {unit!r}; expected the number's unit, '-' for none", path)
    return float(value), unit, {"kind": "number"}


RESOLVERS = {
    "constant": _constant,
    "number": _number,
    "case": _case,
    "assumption": _assumption,
    "catalogue": _catalogue,
    "stored": _stored,
    "calculation": _calculation,
}


def _operand(context, reference, position):
    """Return one operand as ``{reference, value, unit, source}``; a bare literal is refused."""
    path = f"operands[{position}]"
    if not isinstance(reference, dict):
        raise _error(
            f"{path} = {reference!r}; expected an object: a reference to a sourced value (one "
            f"of {', '.join(SOURCED_KINDS)}), {{\"constant\": \"pi\"}} or "
            f"{{\"number\": 24, \"unit\": \"h\"}}",
            path,
        )
    kinds = [kind for kind in REFERENCE_KINDS if kind in reference]
    extra = set(reference) - set(REFERENCE_KINDS) - {"path", "unit"}
    misplaced = ("path" in reference and kinds != ["stored"]) or (
        "unit" in reference and kinds != ["number"]
    )
    if len(kinds) != 1 or extra or misplaced:
        raise _error(
            f"{path} = {reference!r}; expected one key of {', '.join(REFERENCE_KINDS)} "
            "(path only beside stored, unit only beside number)",
            path,
        )
    value, unit, source = RESOLVERS[kinds[0]](context, reference, path)
    return {"reference": reference, "value": value, "unit": unit, "source": source}


def _name(operand):
    """Return how an operand reads in the expression, such as ``catalogue:drilling-nl``."""
    reference = operand["reference"]
    kind = next(kind for kind in REFERENCE_KINDS if kind in reference)
    if kind == "number":
        return f"{operand['value']:g} {operand['unit']} (plain)"
    if kind == "constant":
        return f"{reference['constant']} [{operand['value']:g} {operand['unit']}]" if operand["unit"] != "-" else reference["constant"]
    suffix = f".{reference['path']}" if kind == "stored" else ""
    return f"{kind}:{reference[kind]}{suffix} [{operand['value']:g} {operand['unit']}]"


def new_id():
    """Return a new calculation id, ``C`` and six hex digits: unique without reading the state.

    NOTE: calculations made at once (one step, or nested runs with their own copy of the state)
    numbered C1, C2 ... from the state they saw, and two took the same id (QA-078).
    """
    return f"C{uuid4().hex[:6]}"


def expression_of(operation, operands, exponent):
    """Return the expression as text, each operand named by its reference and value."""
    names = [_name(operand) for operand in operands]
    signs = {"add": " + ", "subtract": " - ", "multiply": " × ", "divide": " / "}
    if operation in signs:
        return signs[operation].join(names)
    if operation == "power":
        return f"({names[0]})^{exponent}"
    return f"{operation}({', '.join(names)})"


def _checked_shape(operation, operands, exponent):
    """Raise when the operation does not fit the number of operands or the exponent."""
    counts = {"subtract": (2, 2), "divide": (2, 2), "power": (1, 1)}
    low, high = counts.get(operation, (2 if operation in ("add", "multiply") else 1, None))
    if len(operands) < low or (high is not None and len(operands) > high):
        wanted = f"{low}" if low == high else f"at least {low}"
        raise _error(f"{operation} takes {wanted} operands, got {len(operands)}", "operands")
    if (operation == "power") != (exponent is not None):
        raise _error("exponent is given with power only, and power needs it", "exponent")


def _base(operand, position):
    """Return ``(base value, dimensions)`` of an operand: its SI value through gemini."""
    import gemini as gm

    path = f"operands[{position}]"
    if operand["unit"] in DIMENSIONLESS:
        return operand["value"], {}
    found, scale, _, _ = _unit_dimensions(operand["unit"], path)
    try:
        si = gm.units.to_si(operand["value"], operand["unit"])
    except gm.errors.ValidationError as error:
        raise _error(f"{path}: {error}", path, "invalid_unit") from error
    return si * scale, found


def _combine(operation, values, exponent):
    """Return the base value of ``operation`` over base values."""
    if operation in ("add", "sum"):
        return math.fsum(values)
    if operation == "subtract":
        return values[0] - values[1]
    if operation == "multiply":
        return math.prod(values)
    if operation == "divide":
        if values[1] == 0:
            raise _error("divide by a value that is zero", "operands[1]")
        return values[0] / values[1]
    if operation == "power":
        return values[0] ** exponent
    if operation == "mean":
        return math.fsum(values) / len(values)
    return min(values) if operation == "min" else max(values)


def _result_dimensions(operation, bases, exponent):
    """Return the dimensions of the result; operands of different dimensions raise."""
    if operation in SAME_DIMENSION:
        first = bases[0][1]
        for position, (_, found) in enumerate(bases[1:], start=1):
            if found != first:
                raise _error(
                    f"{operation} needs one dimension: operands[0] is {_described(first)}, "
                    f"operands[{position}] is {_described(found)}",
                    f"operands[{position}]",
                )
        return dict(first)
    total = {}
    if operation == "power":
        _merge(total, bases[0][1], exponent)
    else:
        _merge(total, bases[0][1], 1)
        for _, found in bases[1:]:
            _merge(total, found, -1 if operation == "divide" else 1)
    return total


def _in_unit(value, found, unit, difference):
    """Return a base value in ``unit`` through gemini's scale and offset; another dimension raises."""
    if unit in DIMENSIONLESS:
        if found:
            raise _error(
                f"unit = {unit!r}, but the result is {_described(found)}; expected one of "
                f"{', '.join(units_of(found)) or 'no unit gemini knows'}",
                "unit",
                "invalid_unit",
            )
        return value
    wanted, scale, gemini_scale, offset = _unit_dimensions(unit, "unit")
    if wanted != found:
        raise _error(
            f"unit = {unit!r} is {_described(wanted)}, but the result is {_described(found)}; "
            f"expected one of {', '.join(units_of(found)) or 'no unit gemini knows'}",
            "unit",
            "invalid_unit",
        )
    return (value / scale - (0 if difference else offset)) / gemini_scale


@tool(effect="compute", idempotent=False, reruns_in_replay=True)
async def calculate(
    context,
    label: str,
    operation: Literal[OPERATIONS],
    operands: list[Any],
    unit: str,
    exponent: int | None = None,
):
    """Derive a value from sourced values and keep it as a calculation with an id.

    Skill `calculator`.
    """
    if not isinstance(label, str) or not label.strip():
        raise _error("label is empty; expected what the value is", "label")
    _checked_shape(operation, operands, exponent)
    resolved = [_operand(context, reference, index) for index, reference in enumerate(operands)]
    if not any(operand["source"]["kind"] in SOURCED_KINDS for operand in resolved):
        raise _error(
            "no operand has a source; expected at least one of "
            f"{', '.join(SOURCED_KINDS)} (plain numbers and constants do not count)",
            "operands",
        )
    bases = [_base(operand, index) for index, operand in enumerate(resolved)]
    found = _result_dimensions(operation, bases, exponent)
    value = _combine(operation, [base for base, _ in bases], exponent)
    result = _in_unit(value, found, unit, difference=operation == "subtract")
    if not math.isfinite(result):
        raise _error(f"the result is {result}, not a finite number", "operands")
    calculation = {
        "id": new_id(),
        "label": label.strip(),
        "operation": operation,
        "expression": expression_of(operation, resolved, exponent),
        "value": float(f"{result:.12g}"),
        "unit": unit,
        "operands": resolved,
    }
    change = {"op": "add", "path": "/calculations/-", "value": calculation}
    version = await context.session.change_state([change])
    return {**calculation, "version": version}

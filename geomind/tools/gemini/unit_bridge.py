"""Unit names gemini refuses that the models write as the sources give them, mapped by set_case.

gemini 0.6.3 takes ``°C/km`` and ``degC/km`` as a temperature gradient (request 31), so no
gradient is mapped here. gemini takes ``mol%`` on a gas fraction and converts it (request 15), so
a gas fraction in ``%`` is only named ``mol%`` here, the same number. Unit names as sources spell
them (``kg/m³``, ``mPa·s``, ``MWth``) become gemini's name of the same unit, ``kg/m3``,
``mPa.s``, ``MW``, only where the key's units hold that name: a name, no factor (#118).
``set_case`` lists each mapping in its result (``converted``) so the case lead puts it in the
confirmation question. A catalogue row's unit with a basis word after it (``EUR/W electric``,
``EUR/MWh cold``) is the unit before the word on an economics key that takes it
(``economics_unit``); the economics question shows the word beside the key's own basis.
"""

import copy
import re

FRACTIONS = (("site", "fluid", "dissolved_gas"), ("utilities", "gas", "composition"))
PERCENT_UNITS = ("%", "mol %")
"""Names of a gas fraction in percent that gemini's ``mol%`` is: the same unit, no factor."""
PERCENT_REASON = "a gas fraction in percent is gemini's mol%, the same number"
SPELLINGS = {"³": "3", "²": "2", "·": "."}
"""Characters of a unit name as sources print it, and gemini's spelling of them."""
UNIT_NAMES = {"MWth": "MW", "MWcool": "MW"}
"""Unit names that say what the power is for, and the unit they are in."""
NAME_REASON = "unit name"
NO_UNIT = ("-", "")
"""How a catalogue writes a number with no unit (a rate, a share)."""
POWER_BASES = ("electric", "shaft", "heat")
"""The powers a per-W cost is stated on: a row on one and a key on another are not converted."""
BASIS = re.compile(r"(per [^(),;]+?) \(([^()]+)\)")
"""A cost basis in gemini's description of an economics key: ``per W of capacity (EUR/W)``."""


def bridged_units(changes):
    """Return ``(changes, converted)``: the changes with the units above mapped, and the list.

    ``converted`` holds ``{path, from: {value, unit}, to: {value, unit}, reason}`` per value; the
    changes are copied, never edited in place.
    """
    changes = copy.deepcopy(changes)
    converted = []
    for section in FRACTIONS:
        gases = _node(changes, section)
        for gas, item in (gases or {}).items():
            unit = _unit(item)
            if unit in PERCENT_UNITS:
                item["unit"] = "mol%"
                value = item.get("value")
                entry = _entry((*section, gas), value, unit, value, "mol%", PERCENT_REASON)
                converted.append(entry)
    converted.extend(_renamed_units(changes, _case_schema(), ()))
    return changes, converted


def gemini_unit_name(unit, accepted):
    """Return gemini's name of ``unit`` when ``accepted`` holds it and not ``unit``, else ``None``.

    ``m³/h`` is ``m3/h``, ``mPa·s`` is ``mPa.s``, ``MWth`` and ``MWcool`` are ``MW``: the same unit.
    """
    if not isinstance(unit, str) or unit in accepted:
        return None
    name = "".join(SPELLINGS.get(char, char) for char in unit.strip())
    name = UNIT_NAMES.get(name, name)
    return name if name in accepted else None


def _case_schema():
    """Return gemini's JSON Schema of a case."""
    import gemini as gm

    return gm.Case.schema()


def _accepted_units(schema):
    """Return the units a field's schema accepts: its ``x-units`` or the ``unit`` enums."""
    if not isinstance(schema, dict):
        return set()
    units = set(schema.get("x-units") or ())
    unit = (schema.get("properties") or {}).get("unit")
    units |= set((unit or {}).get("enum") or ())
    for branch in schema.get("anyOf") or ():
        units |= _accepted_units(branch)
    return units


def _child_schema(schema, key):
    """Return the schema of ``key`` under an object schema, or ``None``."""
    if not isinstance(schema, dict):
        return None
    child = (schema.get("properties") or {}).get(key)
    extra = schema.get("additionalProperties")
    return child if child is not None else extra if isinstance(extra, dict) else None


def _renamed_units(changes, schema, path):
    """Give each ``unit`` under ``changes`` gemini's name where its key takes it; return entries."""
    if not isinstance(changes, dict) or schema is None:
        return []
    name = gemini_unit_name(changes.get("unit"), _accepted_units(schema))
    if name is not None:
        given, changes["unit"] = changes["unit"], name
        value = changes.get("value")
        return [_entry(path, value, given, value, name, NAME_REASON)]
    entries = []
    for key, item in changes.items():
        entries.extend(_renamed_units(item, _child_schema(schema, key), (*path, key)))
    return entries


def _node(changes, path):
    """Return the dict at ``path`` of a merge patch, or ``None``."""
    node = changes
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else None


def _unit(item):
    """Return the stripped unit of a value object, or ``None``."""
    unit = item.get("unit") if isinstance(item, dict) else None
    return unit.strip() if isinstance(unit, str) else None


def _entry(path, value, unit, new_value, new_unit, reason):
    """Return one ``converted`` entry."""
    return {
        "path": ".".join(path),
        "from": {"value": value, "unit": unit},
        "to": {"value": new_value, "unit": new_unit},
        "reason": reason,
    }


def bridged_requirements(requirements):
    """Return ``(requirements, converted)``: each requirement's unit under gemini's name of it.

    A requirement's ``unit`` may be any unit gemini knows, so ``m³/h`` becomes ``m3/h``; the
    requirements are copied, never edited in place.
    """
    import gemini as gm

    requirements = copy.deepcopy(requirements)
    known = set(gm.units.names())
    converted = []
    for name, item in requirements.items():
        unit = item.get("unit") if isinstance(item, dict) else None
        renamed = gemini_unit_name(unit, known)
        if renamed is not None:
            item["unit"] = renamed
            converted.append(_entry(("requirements", name), None, unit, None, renamed, NAME_REASON))
    return requirements, converted


def economics_schema(key):
    """Return gemini's schema of the economics key ``key`` (``capex.heat_pump``), or ``None``."""
    import gemini as gm

    node = gm.case.Economics.schema()
    for part in key.removeprefix("economics.").split("."):
        node = _child_schema(node, part)
    return node


def _ratio(unit):
    """Tell whether ``unit`` is a ratio of one unit to itself (``kg CO2e/kg CH4``): no dimension."""
    top, slash, bottom = unit.partition("/")
    top, bottom = top.split(), bottom.split()
    return bool(slash and top and bottom and top[0] == bottom[0])


def _unitless(given):
    """Return ``(unit, note, accepted)`` of a row's unit on a key that takes no unit (QA-004).

    gemini refuses any unit there, after the user's approve all; so a ratio of one unit to
    itself (``kg CO2e/kg CH4``) is dropped with a note, and any other unit is refused before the
    user is asked, ``accepted`` then ``["no unit"]`` (a percent is a fraction there: 0.05).
    """
    if given in NO_UNIT:
        return None, None, []
    if _ratio(given):
        return None, f"the row's unit is {given}; set with no unit, as the key takes", []
    return None, None, ["no unit (a fraction or a ratio, such as 0.05 for 5 %)"]


def bracketed(unit, accepted):
    """Return ``EUR/(W/K)`` for ``EUR/W/K`` when the key takes the bracketed form (QA-243)."""
    if not isinstance(unit, str) or unit in accepted or unit.count("/") < 2 or "(" in unit:
        return unit
    head, _, rest = unit.partition("/")
    form = f"{head}/({rest})"
    return form if form in accepted else unit


def economics_unit(key, unit):
    """Return ``(unit, note, accepted)`` of an economics value's ``unit`` as its key takes it.

    ``unit`` is the key's unit, ``None`` when the key takes none (``-``) or when it refuses the
    unit, which ``accepted`` (the units it takes) then tells. A unit with a basis word after it
    (``EUR/W electric``) is the unit before the word when the key takes it, never a factor;
    ``note`` then says the row's unit and the basis the key reads that unit on (E2E-10).
    """
    schema = economics_schema(key)
    accepted = sorted(_accepted_units(schema))
    given = unit.strip() if isinstance(unit, str) else unit
    given = bracketed(given, accepted)
    if given is None or given in accepted:
        return given, None, accepted
    if not accepted and "unit" not in (schema or {}).get("properties", {}):
        return _unitless(given)
    if not accepted:
        return (None, None, accepted) if given in NO_UNIT else (given, None, accepted)
    head, _, words = given.partition(" ")
    name = head if head in accepted else gemini_unit_name(head, accepted)
    if name is None:
        return None, None, accepted
    if not words:
        return name, None, accepted
    basis = dict((unit, text) for text, unit in BASIS.findall(schema.get("description") or ""))
    note = f"the row's unit is {given}; set as {name}"
    if name not in basis:
        return name, note, accepted
    note += f", which the key reads {basis[name]}"
    row_basis = [word for word in POWER_BASES if word in words.lower().split()]
    key_basis = [word for word in POWER_BASES if word in basis[name].lower().split()]
    if row_basis and key_basis and row_basis != key_basis:
        note += f"; the row is {row_basis[0]}, not {key_basis[0]} power: not converted, "
        note += "the user decides"
    return name, note, accepted

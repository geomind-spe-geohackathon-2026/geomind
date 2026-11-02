"""What a gemini error tells the model beyond gemini's own message: the next call to make.

Two rejections are explained. A study that needs a search range the plant does not state gets the
``set_ranges`` call that adds it (the unit of the parameter from the plant, never a number). A
unit gemini does not know gets the units gemini accepts, read from ``gm.units``.
"""

import difflib
import re
from contextlib import contextmanager

from geomind.errors import ToolError
from geomind.utils.strings import join_names

UNIT_GIVEN = re.compile(r"unit = '([^']*)'")
UNIT_LISTED = ("accepted units", "expected a unit of")
RANGE_SUFFIX = ".range"
SHOWN_LEAVES = 12
ASK = (
    "the range is not in the case and only the user or the case gives one: ask the user with "
    "ask_user, proposing values with a one-line reason, and after the user confirms call"
)
NO_RANGE = "states no range and no options"


def leaf_node(plant, path):
    """Return the plant file's node of the leaf ``path`` (as ``depth``), or ``{}``."""
    data = plant.to_dict()
    section, _, leaf = path.partition(".") if path.startswith("size.") else ("params", "", path)
    node = data.get(section, {})
    for part in leaf.split("."):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}


def range_entry(plant, path):
    """Return the ``ranges`` entry that would state the range of a leaf, bounds as placeholders."""
    unit = leaf_node(plant, path).get("unit")
    if unit in (None, "-"):
        return {"min": "<min>", "max": "<max>"}
    return {
        "min": {"value": "<min>", "unit": unit},
        "max": {"value": "<max>", "unit": unit},
    }


def set_ranges_call(design, entries):
    """Return the text of the ``set_ranges`` call that states ``entries`` on a design."""
    shown = repr(entries).replace("'<min>'", "<min>").replace("'<max>'", "<max>")
    return f"set_ranges(design={design!r}, ranges={shown}, name='<new design name>')"


def missing_paths(error):
    """Return the leaves whose ``range`` gemini reports as missing, in order."""
    found = []
    for problem in error.problems:
        path = problem.get("path") or ""
        if problem.get("code") == "missing_value" and path.endswith(RANGE_SUFFIX):
            found.append(path.removeprefix("params.").removesuffix(RANGE_SUFFIX))
    return found


def lacking(plant, path):
    """Whether the plant states no complete range for the leaf."""
    found = plant.ranges.get(path)
    return found is None or found.min is None or found.max is None


def numeric_leaves(node, prefix=""):
    """Return ``{path: unit}`` of the numeric leaves under a ``params`` node of a plant file."""
    found = {}
    for key, child in node.items():
        if not isinstance(child, dict):
            continue
        path = f"{prefix}{key}"
        value = child.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            found[path] = child.get("unit") or "no unit"
            continue
        found |= numeric_leaves(child, f"{path}.")
    return found


def searchable(plant):
    """Return the leaves a plant file may state a range for, with their units.

    These are ``size.doublets`` when the plant takes it and every numeric leaf of ``params``; they
    are the ``ranges`` of ``gm.plants.capabilities()`` for the class, read from the plant itself.
    """
    data = plant.to_dict()
    found = {"size.doublets": "count"} if "doublets" in data.get("size", {}) else {}
    return found | numeric_leaves(data.get("params", {}))


def missing_range_text(error, plants):
    """Return the lines that tell which ranges to set for the plants, or ``""`` for none."""
    lines = []
    for path in missing_paths(error):
        for design, plant in plants.items():
            if lacking(plant, path):
                call = set_ranges_call(design, {path: range_entry(plant, path)})
                lines.append(f"{design} has no range for {path}; {ASK} {call}")
    return "; ".join(lines)


def no_search_text(error, plants):
    """Return the text for a search over plants that state no range and no options."""
    if NO_RANGE not in str(error):
        return ""
    lines = []
    for design, plant in plants.items():
        if not plant.ranges and not plant.options:
            found = [f"{path} [{unit}]" for path, unit in searchable(plant).items()]
            more = f" and {len(found) - SHOWN_LEAVES} more" if len(found) > SHOWN_LEAVES else ""
            leaves = join_names(found[:SHOWN_LEAVES]) + more
            call = set_ranges_call(design, {"<leaf>": {"min": "<min>", "max": "<max>"}})
            lines.append(f"{design} can state a range on: {leaves}; {ASK} {call}")
    return "; ".join(lines)


@contextmanager
def range_guidance(plants):
    """Re-raise a gemini rejection for a missing range or option as a tool error with the fix.

    ``plants`` is ``{design reference: gemini plant}`` of the call. Any other error passes on as
    it is. The tool error keeps gemini's message, its path and its code.
    """
    import gemini as gm

    try:
        yield
    except gm.errors.ValidationError as error:
        text = missing_range_text(error, plants) or no_search_text(error, plants)
        if not text:
            raise
        raise ToolError(f"{error}. {text}", code=error.code, path=error.path) from error


def candidate_unit(given, names):
    """Return the known unit ``given`` most likely means: its longest prefix, else a near name."""
    prefixes = [name for name in names if given.startswith(name)]
    if prefixes:
        return max(prefixes, key=len)
    near = difflib.get_close_matches(given, names, n=1)
    return near[0] if near else None


def accepted_units(unit=None, quantity=None):
    """Return the unit names gemini accepts for a quantity, or for the dimension of ``unit``."""
    import gemini as gm

    if quantity is not None:
        return gm.units.names(quantity)
    names = gm.units.names()
    return [name for name in names if gm.units.si_unit(name) == gm.units.si_unit(unit)]


def unit_text(error, quantity=None):
    """Return gemini's unit message with the accepted units, or ``""`` for any other error."""
    import gemini as gm

    message = str(error)
    given = UNIT_GIVEN.search(message)
    if (
        error.code != "invalid_unit"
        or given is None
        or any(mark in message for mark in UNIT_LISTED)
    ):
        return ""
    if quantity is not None:
        units = join_names(accepted_units(quantity=quantity))
        return f"{message}; units gemini accepts for {quantity}: {units}"
    unit = candidate_unit(given.group(1), gm.units.names())
    if unit is None:
        return f"{message}; gm.units.names() lists every unit gemini accepts"
    units = join_names(accepted_units(unit))
    return f"{message}; did you mean {unit!r}? units of its dimension that gemini accepts: {units}"


def explained(error, quantity=None):
    """Return the error as gemini's problem dict, its message extended with the units it accepts."""
    problem = error.to_dict()
    text = unit_text(error, quantity)
    return {**problem, "message": text} if text else problem


def unit_error(error, quantity):
    """Return a tool error for a rejected unit, naming the units gemini accepts for ``quantity``."""
    return ToolError(explained(error, quantity)["message"], code=error.code, path=error.path)

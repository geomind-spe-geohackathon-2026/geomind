"""geomind converts no unit itself: every conversion is gemini's, one source of truth."""

import ast

import pytest

from tests.fixtures import ROOT
from tests.unit.test_gemini_names import geomind_files

FACTORS = {0.001, 1e-6, 0.01, 100, 3.6, 60, 3600, 86400, 8760, 31536000, 31557600, 273.15, 1e5, 1e6}
"""Numbers that only a unit conversion uses: milli, micro, percent, minutes, hours, days, years,
kelvin."""
ALLOWED = {}
"""The one-line exceptions, ``(path, line) -> reason``; each goes when its gemini request lands."""
UNIT_NAMES = {
    "ms",
    "s",
    "min",
    "h",
    "d",
    "yr",
    "K",
    "degC",
    "W",
    "kW",
    "MW",
    "Pa",
    "bar",
    "J",
    "MWh",
}


def conversion_lines(source):
    """Return the lines of a module that hold a unit factor or map a unit name to a number."""
    found = []
    for node in ast.walk(ast.parse(source)):
        is_number = isinstance(node, ast.Constant) and type(node.value) in (int, float)
        if is_number and node.value in FACTORS:
            found.append(node.lineno)
        if isinstance(node, ast.Dict) and _maps_units(node):
            found.append(node.lineno)
    return found


def _maps_units(node):
    """Tell whether a dict literal maps unit names to numbers, a factor table."""
    keys = [key.value for key in node.keys if isinstance(key, ast.Constant)]
    numbers = [value for value in node.values if isinstance(value, ast.Constant)]
    return bool(keys) and set(keys) <= UNIT_NAMES and len(numbers) == len(keys)


@pytest.mark.parametrize(
    "path", [path for path in geomind_files() if path.endswith(".py")], ids=lambda path: path
)
def test_the_package_has_no_unit_factor(path):
    """A conversion goes through gemini (``gm.units.convert``, ``Quantity.to``, ``units=``)."""
    source = (ROOT / path).read_text()
    lines = source.splitlines()
    found = [
        number
        for number in conversion_lines(source)
        if (path, lines[number - 1].strip()) not in ALLOWED
    ]
    assert found == []


def test_each_exception_is_still_in_its_file():
    """An exception whose line is gone is removed, so the allowlist stays as narrow as it is."""
    for path, line in ALLOWED:
        assert line in [text.strip() for text in (ROOT / path).read_text().splitlines()]


def test_the_check_sees_a_factor_and_a_factor_table():
    """The check finds what it is meant to find."""
    assert conversion_lines("x = seconds / 3600\n") == [1]
    assert conversion_lines('SECONDS = {"s": 1.0, "h": 3600.0}\n') != []
    assert conversion_lines("TOKENS = 1000\n") == []
    assert conversion_lines("fraction = percent / 100\n") == [1]

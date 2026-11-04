"""What a gemini error tells the model: the missing range's fix and the units gemini accepts."""

import pytest

from geomind.errors import ToolError
from geomind.tools.dispatch import error_output
from geomind.tools.gemini.explain import (
    candidate_unit,
    explained,
    numeric_leaves,
    range_entry,
    searchable,
    set_ranges_call,
    unit_error,
)
from tests.fixtures.cases import example_plant, warm_gemini


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Pay for the gemini import outside the timed calls."""
    warm_gemini()


def rejected_unit(unit="day"):
    """Return the error gemini raises for a unit it does not know."""
    import gemini as gm

    with pytest.raises(gm.errors.ValidationError) as caught:
        gm.units.Quantity(1, unit)
    return caught.value


def test_a_rejected_unit_gets_gemini_message_and_the_units_of_its_dimension():
    """``day`` is read as ``d``, and the durations gemini accepts are listed."""
    text = explained(rejected_unit("day"))["message"]
    assert text.startswith("Quantity: unit = 'day'; expected a known unit")
    assert "did you mean 'd'" in text
    assert "h" in text and "min" in text


def test_the_units_come_from_gemini_for_a_named_quantity():
    """With the quantity known, the list is gemini's own for it."""
    import gemini as gm

    error = unit_error(rejected_unit("hour"), "duration")
    assert isinstance(error, ToolError)
    for unit in gm.units.names("duration"):
        assert unit in str(error)
    assert error.code == "invalid_unit"


def test_an_error_that_is_not_a_unit_error_passes_through_unchanged():
    """Only a rejected unit is extended."""
    import gemini as gm

    error = gm.errors.ValidationError("x is missing", path="x", code="missing_value")
    assert explained(error) == error.to_dict()
    assert error_output(error) == {"error": error.to_dict()}


def test_the_dispatch_path_extends_a_rejected_unit_for_every_tool():
    """error_output is the shared path, so a tool needs nothing of its own."""
    message = error_output(rejected_unit("hour"))["error"]["message"]
    assert "did you mean 'h'" in message


def test_a_unit_gemini_lists_already_is_not_repeated():
    """A message that has the accepted units stays as gemini wrote it."""
    import gemini as gm

    error = gm.errors.ValidationError(
        "p: unit = 'foo'; expected a unit of power: MW", code="invalid_unit"
    )
    assert explained(error)["message"] == str(error)


def test_candidate_unit_prefers_the_longest_known_prefix():
    """``minute`` means ``min``, not ``m``; a name with no prefix falls back to a near name."""
    names = ["m", "min", "s"]
    assert candidate_unit("minute", names) == "min"
    assert candidate_unit("zzz", names) is None


def test_the_set_ranges_call_has_placeholders_and_the_unit_of_the_leaf():
    """A leaf with a unit gets quantities with its unit; a count gets plain bounds; no numbers."""
    plant = example_plant("shallow_district")
    depth = set_ranges_call("design/a", {"depth": range_entry(plant, "depth")})
    assert depth == (
        "set_ranges(design='design/a', ranges={'depth': {'min': {'value': <min>, 'unit': 'm'}, "
        "'max': {'value': <max>, 'unit': 'm'}}}, name='<new design name>')"
    )
    count = set_ranges_call("design/a", {"size.doublets": range_entry(plant, "size.doublets")})
    assert "{'size.doublets': {'min': <min>, 'max': <max>}}" in count


def test_searchable_leaves_cover_the_ranges_of_the_plant():
    """Every leaf that has a range is a leaf that could state one."""
    plant = example_plant("shallow_district")
    assert set(plant.ranges) <= set(searchable(plant))
    assert numeric_leaves({"a": {"value": 1, "unit": "m"}, "b": {"c": {"value": True}}}) == {
        "a": "m"
    }


def test_the_same_problem_on_many_rows_is_one_line():
    """Three rows of one file with the same problem: one line, the count and the row span."""
    import gemini as gm

    from geomind.tools.gemini.explain import shown_message

    problems = [
        {
            "path": "f",
            "code": "invalid_value",
            "message": f"f: a.csv row {row} t = '{row}' bad",
            "suggestions": [],
        }
        for row in (2, 3, 7)
    ]
    message = shown_message(gm.errors.ValidationError.of(problems))
    assert message == "f: a.csv row 2 t = '2' bad (the same on 3 rows, rows 2 to 7)"


def test_a_unit_of_a_key_with_two_bases_lists_the_units_of_both():
    """E2E-10: ``capex.ice_storage`` takes money per volume or per energy.

    gemini says "a unit of money per volume or money per energy"; the two were joined into one
    quantity, ``money_per_volume_or_money_per_energy``, which ``gm.units`` refused, and the
    user's approve all was lost. Each quantity is looked up alone.
    """
    import gemini as gm

    from geomind.tools.gemini.explain import unit_retry

    economics = {"capex": {"ice_storage": {"value": 23249.87, "unit": "EUR/MWh cold"}}}
    data = {"format": 1, "kind": "economics", "name": "e", **economics}
    with pytest.raises(gm.errors.ValidationError) as caught:
        gm.case.Economics.from_dict(data)
    suggestions = unit_retry(caught.value, {"economics": economics})
    accepted = next(item for item in suggestions if "accepted units" in item)
    assert "EUR/m3" in accepted and "EUR/MWh" in accepted
    assert "economics.capex.ice_storage = {'value': 23249.87, 'unit': 'EUR/MWh'}" in suggestions

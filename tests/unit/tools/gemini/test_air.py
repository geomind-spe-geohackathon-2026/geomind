"""The air pressure of a site from its elevation: code computes it, never the model."""

import pytest

from geomind.errors import ToolError
from geomind.tools.gemini.air import CITATION, isa_pressure, pressure_from_elevation
from tests.unit.tools.gemini.test_case import edited, loaded, state_after


def test_the_isa_pressure_is_the_standard_atmosphere_s():
    """ISO 2533:1975: 101325 Pa at sea level, about 89875 Pa at 1000 m."""
    assert isa_pressure(0) == 101325
    assert isa_pressure(1000) == pytest.approx(89874.56, abs=0.01)


def test_an_elevation_becomes_the_isa_pressure_with_its_source():
    """The unit goes through gemini: 1000 ft is 304.8 m."""
    changes = {"site": {"air": {"pressure": {"elevation": {"value": 1000, "unit": "ft"}}}}}
    changes, (entry,) = pressure_from_elevation(changes)
    air = changes["site"]["air"]
    assert air["pressure"] == {"value": pytest.approx(isa_pressure(304.8)), "unit": "Pa"}
    assert CITATION in air["about"]["pressure"] and CITATION in entry["reason"]
    assert entry["from"] == {"elevation": {"value": 1000, "unit": "ft"}}
    assert entry["path"] == "site.air.pressure" and entry["to"]["unit"] == "Pa"


def test_a_pressure_and_no_air_stay_as_given():
    """No default: without an elevation nothing is set."""
    given = {"site": {"air": {"pressure": {"value": 1, "unit": "bar"}}}}
    assert pressure_from_elevation(given) == (given, [])
    assert pressure_from_elevation({"site": {"ground": {}}}) == ({"site": {"ground": {}}}, [])


@pytest.mark.parametrize(
    "pressure",
    [
        {"elevation": {"value": 10, "unit": "kg"}},
        {"elevation": 120},
        {"elevation": {"value": "high", "unit": "m"}},
        {"elevation": {"value": 10, "unit": "m"}, "value": 1},
        {"elevation": {"value": 50, "unit": "km"}},
    ],
)
def test_a_wrong_elevation_is_refused_naming_the_form(pressure):
    """A unit of no length, a text, a pressure beside it, a height above the atmosphere."""
    with pytest.raises(ToolError) as raised:
        pressure_from_elevation({"site": {"air": {"pressure": pressure}}})
    assert raised.value.path.startswith("site.air.pressure.elevation")


async def test_set_case_sets_the_isa_pressure_and_lists_it_for_confirmation():
    """The case lead gives the elevation; set_case stores the pressure and says where from."""
    session, problem = await loaded("shallow_district")
    changes = {"site": {"air": {"pressure": {"elevation": {"value": 120, "unit": "m"}}}}}
    result = await edited(session, problem, {"changes": changes})
    assert result.is_error is False, result.output
    air = state_after(session, problem).case["site"]["air"]
    assert air["pressure"] == {"value": pytest.approx(isa_pressure(120)), "unit": "Pa"}
    (entry,) = result.output["converted"]
    assert entry["path"] == "site.air.pressure" and CITATION in entry["reason"]
    assert changes["site"]["air"]["pressure"] == {"elevation": {"value": 120, "unit": "m"}}

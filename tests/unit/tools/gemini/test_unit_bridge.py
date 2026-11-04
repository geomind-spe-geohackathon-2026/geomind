"""The unit names gemini refuses that set_case maps (#115, #118); gradients are gemini's (31)."""

from geomind.tools.gemini.unit_bridge import bridged_units, gemini_unit_name


def test_a_gas_in_percent_is_named_mol_percent_and_left_to_gemini():
    """A gas in ``%`` is only renamed ``mol%``: gemini 0.6.2 converts it (request 15)."""
    gas = {"N2": {"value": 10, "unit": "%", "range": {"min": 5, "max": 20}}}
    changes = {
        "utilities": {"gas": {"composition": gas}},
        "site": {"fluid": {"density": {"value": 1030, "unit": "kg/m3"}}},
    }
    bridged, converted = bridged_units(changes)
    assert bridged["utilities"]["gas"]["composition"]["N2"] == {
        "value": 10,
        "unit": "mol%",
        "range": {"min": 5, "max": 20},
    }
    assert bridged["site"] == changes["site"]
    assert [entry["path"] for entry in converted] == ["utilities.gas.composition.N2"]
    given = {"utilities": {"gas": {"composition": {"N2": {"value": 10, "unit": "mol%"}}}}}
    assert bridged_units(given) == (given, [])


def test_a_gas_without_a_unit_and_a_gradient_in_degrees_per_km_stay_as_given():
    """Only the named units are touched: a bare value is no percentage, °C/km is gemini's (31)."""
    changes = {
        "site": {
            "ground": {"gradient": {"value": 30, "unit": "°C/km"}},
            "fluid": {"dissolved_gas": {"CH4": {"value": 80}}},
        }
    }
    assert bridged_units(changes) == (changes, [])


def test_a_unit_name_is_mapped_only_to_a_name_the_key_accepts():
    """#118: ``MWth`` is ``MW`` on a power; a name the key lacks stays for gemini to judge."""
    assert gemini_unit_name("MWth", {"MW", "kW"}) == "MW"
    assert gemini_unit_name("m³/h", {"m3/h"}) == "m3/h"
    assert gemini_unit_name("MWth", {"K", "degC"}) is None
    assert gemini_unit_name("MW", {"MW"}) is None
    changes = {"demand": {"heating": {"power": {"file": "d.csv", "column": "q", "unit": "MWth"}}}}
    bridged, (entry,) = bridged_units(changes)
    assert bridged["demand"]["heating"]["power"]["unit"] == "MW"
    assert (entry["path"], entry["reason"]) == ("demand.heating.power", "unit name")
    assert changes["demand"]["heating"]["power"]["unit"] == "MWth"
    odd = {"site": {"ground": {"surface_temperature": {"value": 12, "unit": "MWth"}}}}
    assert bridged_units(odd) == (odd, [])

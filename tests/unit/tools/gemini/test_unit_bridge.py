"""The units gemini 0.6.1 refuses that set_case maps until gemini requests 15 and 31 (#115)."""

from geomind.tools.gemini.unit_bridge import bridged_units, gemini_unit_name, percent_fraction


def test_the_bridge_scales_a_range_and_the_utilities_gas():
    """The bounds of a gas fraction in percent are fractions too; other sections are left alone."""
    changes = {
        "utilities": {
            "gas": {
                "composition": {"N2": {"value": 10, "unit": "mol%", "range": {"min": 5, "max": 20}}}
            }
        },
        "site": {"fluid": {"density": {"value": 1030, "unit": "kg/m3"}}},
    }
    bridged, converted = bridged_units(changes)
    assert bridged["utilities"]["gas"]["composition"]["N2"] == {
        "value": 0.1,
        "range": {"min": 0.05, "max": 0.2},
    }
    assert bridged["site"] == changes["site"]
    assert [entry["path"] for entry in converted] == ["utilities.gas.composition.N2"]


def test_a_gas_without_a_unit_and_a_gradient_in_k_per_km_stay_as_given():
    """Only the named units are touched: a bare value is no percentage."""
    changes = {
        "site": {
            "ground": {"gradient": {"value": 30, "unit": "K/km"}},
            "fluid": {"dissolved_gas": {"CH4": {"value": 80}}},
        }
    }
    assert bridged_units(changes) == (changes, [])


def test_percent_fraction_is_the_value_over_a_hundred():
    """The one conversion geomind does, until gemini request 15."""
    assert percent_fraction(20) == 0.2


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

"""The numbers of the official brief, held in one place."""

from geomind.tools.gemini.brief import SCHEDULE_RULES


def test_the_schedule_rules_are_the_hard_limits_of_the_brief():
    """1 to 3 doublets run between 50 and 300 m3/h and cool the brine by at most 40 K."""
    assert SCHEDULE_RULES["doublet_flow"] == {"min": "50 m3/h", "max": "300 m3/h"}
    assert SCHEDULE_RULES["max_brine_cooling"] == "40 K"


def test_the_operating_days_wait_for_gemini():
    """``gm.schedule`` raises ``NotImplementedYet`` for anything but ``None``."""
    assert SCHEDULE_RULES["operating_days"] is None


def test_geothermal_heat_comes_first():
    """The doublets, then a heat pump, then a boiler cover the demand."""
    assert SCHEDULE_RULES["order"] == ["geothermal", "heat_pump", "boiler"]

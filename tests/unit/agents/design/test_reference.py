"""Each design agent carries gemini's description of its own modules, made from gemini (B2)."""

import pytest

from geomind.agents.design.energy import EnergySystemsEngineer
from geomind.agents.design.integration import IntegrationEngineer
from geomind.agents.design.process import ProcessEngineer
from geomind.agents.design.reference import OWNED_MODULES
from geomind.agents.design.reservoir import ReservoirEngineer
from geomind.agents.design.well import WellEngineer
from geomind.tools.gemini import patch_plant

ENGINEERS = {"reservoir": ReservoirEngineer, "well": WellEngineer, "energy": EnergySystemsEngineer}


def test_every_owned_module_is_one_of_gemini_s():
    """A module gemini renames or drops fails here, not in a live run."""
    import gemini as gm

    owned = {name for names in OWNED_MODULES.values() for name in names}
    assert owned <= set(gm.modules.names())


@pytest.mark.parametrize("discipline", sorted(ENGINEERS))
def test_an_engineer_s_prompt_holds_its_modules_and_its_workflow(discipline):
    """D2: 6 to 16 describe_module calls each; the prompt now holds them, said once."""
    text = ENGINEERS[discipline]().prompt.render()
    for name in OWNED_MODULES[discipline]:
        assert f"### {name} (" in text
    assert "one `patch_plant` call with all your changes" in text
    assert "Stop when no issue names a path you own" in text
    assert "give it in the case" in text and "at most twelve lines" in text


def test_the_well_engineer_sees_the_section_list_form():
    """#74: a well path's sections are one quantity holding a list."""
    text = WellEngineer().prompt.render()
    assert "### ProductionWell (wells)" in text and '{"value": [500, 2000], "unit": "m"}' in text


def test_the_process_engineer_builds_from_the_class_s_whole_file():
    """B2: a header-only class plant lists about a hundred inner values as missing."""
    text = ProcessEngineer().prompt.render()
    assert "## Plant classes (from gemini)" in text and "- HeatingHeatPumpCoolingPlant:" in text
    assert "Don't build from the header alone" in text


def test_the_integration_engineer_has_every_module_s_ports():
    """Its ports come from gemini, so it needs no describe_module call to connect."""
    text = IntegrationEngineer().prompt.render()
    assert (
        "## Module ports (from gemini)" in text and "- ProductionWell: in bottom_in (brine)" in text
    )


def test_patch_plant_takes_several_modules_in_one_patch():
    """The docstring asked for one module's values at a time; the engineers patched 6 times."""
    assert "of one module or several, in one patch" in " ".join(patch_plant.description.split())


def test_the_lead_records_the_design_before_it_finishes():
    """#78: nemotron checked a handed design, then finished without design.reference/result."""
    from geomind.agents.design.lead import DesignLead

    text = " ".join(DesignLead().prompt.content.split())
    assert "Before `finish`, always one `update_state` with `design.reference` and" in text

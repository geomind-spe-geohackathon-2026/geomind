"""Which part of a plant file each engineer of the design team may change."""

import pytest

from geomind.context import ProblemState
from geomind.engine import Context
from geomind.errors import ToolError
from geomind.tools.gemini.ownership import (
    check_ownership,
    foreign_changes,
    owner_of,
    parameter_paths,
)
from tests.fixtures.sessions import StubSession

OWNERS = {"d0.reservoir": "reservoir", "d0.well": "well", "heat_pump": "energy"}


class Engineer:
    """An agent of one discipline, as the session holds it."""

    def __init__(self, discipline):
        """Keep the discipline."""
        self.discipline = discipline


def context_of(discipline, owners=OWNERS):
    """Return a context whose session runs an agent of ``discipline``."""
    session = StubSession()
    session.agent = Engineer(discipline) if discipline else object()
    problem = ProblemState(design={"owners": owners})
    return Context(session=session, problem=problem)


def test_a_patch_names_each_parameter_it_sets_or_removes():
    """A leaf is a ``{value, unit}`` or a removal; its path is dotted from ``params``."""
    params = {"d0": {"reservoir": {"pressure": {"value": 1, "unit": "bar"}, "skin": None}}}
    assert parameter_paths(params) == ["d0.reservoir.pressure", "d0.reservoir.skin"]


def test_the_longest_owned_prefix_decides():
    """``d0.reservoir.pressure`` is the reservoir engineer's; an unlisted path is nobody's."""
    assert owner_of("d0.reservoir.pressure", OWNERS) == "reservoir"
    assert owner_of("d0.well.section_length", OWNERS) == "well"
    assert owner_of("d0.esp.stage_count", OWNERS) is None


def test_sections_belong_to_the_process_and_integration_engineers():
    """The modules are the process engineer's, the connections the integration engineer's."""
    changes = {"modules": {}, "connections": [], "params": {"heat_pump": {"capacity": {}}}}
    assert foreign_changes(changes, "energy", OWNERS) == [
        ("modules", "process"),
        ("connections", "integration"),
    ]
    assert foreign_changes({"connections": []}, "integration", OWNERS) == []


def test_an_engineer_is_refused_another_discipline_s_part():
    """The reservoir engineer may set the reservoir, not the well; the error says whose it is."""
    reservoir = {"params": {"d0": {"reservoir": {"pressure": {"value": 1, "unit": "bar"}}}}}
    check_ownership(context_of("reservoir"), reservoir, "patch_plant")
    well = {"params": {"d0": {"well": {"section_length": {"value": [1], "unit": "m"}}}}}
    with pytest.raises(ToolError, match="the well engineer's") as raised:
        check_ownership(context_of("reservoir"), well, "patch_plant")
    assert raised.value.code == "not_allowed"
    assert raised.value.path == "changes.params.d0.well.section_length"


def test_a_part_with_no_owner_yet_says_so():
    """Before the process engineer records owners, an engineer's patch is refused with why."""
    patch = {"params": {"d0": {"reservoir": {"skin": {"value": 0}}}}}
    with pytest.raises(ToolError, match="design.owners names none"):
        check_ownership(context_of("reservoir", owners={}), patch, "patch_plant")


def test_the_design_lead_and_other_agents_change_anything():
    """An agent of no discipline is not checked."""
    check_ownership(context_of(None), {"modules": {}, "params": {"x": {}}}, "patch_plant")


def test_an_owner_named_with_params_in_front_is_found():
    """#56: owners were recorded as ``params.d0.reservoir``; every engineer's patch was refused."""
    owners = {"params.d0.reservoir": "reservoir", "params.d0": "well"}
    assert owner_of("d0.reservoir.pressure", owners) == "reservoir"
    assert owner_of("d0.depth", owners) == "well"
    patch = {"params": {"d0": {"reservoir": {"pressure": {"value": 1, "unit": "bar"}}}}}
    check_ownership(context_of("reservoir", owners), patch, "patch_plant")

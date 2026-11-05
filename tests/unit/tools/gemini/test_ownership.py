"""Which part of a plant file each engineer of the design team may change."""

import pytest

from geomind.context import ProblemState
from geomind.engine import Context
from geomind.errors import ToolError
from geomind.tools.gemini.ownership import (
    check_ownership,
    default_owners,
    foreign_changes,
    owner_of,
    parameter_paths,
    placed_parameters,
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


def test_the_bypass_is_the_integration_engineer_s():
    """The plant's ``bypass`` (gemini 0.6.2) is wiring: the integration engineer sets it.

    It belonged to no discipline, so the integration engineer's patch of it was refused.
    """
    changes = {"bypass": {"boiler": {"fluid_in": "fluid_out"}, "gas_grid": {}}}
    assert foreign_changes(changes, "integration", OWNERS) == []
    assert foreign_changes(changes, "energy", OWNERS) == [("bypass", "integration")]
    check_ownership(context_of("integration"), changes, "patch_plant")


def test_the_superstructure_is_the_process_engineer_s():
    """``optional`` and ``choices`` belong to the process engineer, like the modules."""
    changes = {"optional": ["boiler"], "choices": {"cold": {"a": [], "b": []}}}
    assert foreign_changes(changes, "process", OWNERS) == []
    assert [path for path, _ in foreign_changes(changes, "energy", OWNERS)] == [
        "optional",
        "choices",
    ]


RUN_OWNERS = {
    "d0.reservoir": "reservoir",
    "d0.well": "well",
    "degasser": "reservoir",
    "heat_pump": "energy",
    "injection_pump": "well",
}
"""The owners the process engineer recorded in the second end-to-end run, in part."""


@pytest.fixture(scope="module")
def plant():
    """Return the example HeatingHeatPumpCoolingPlant as its plant file dict."""
    from tests.fixtures.cases import example_plant

    return example_plant("hackathon_2026", "HeatingHeatPumpCoolingPlant").to_dict(structure=True)


RUN_PATCHES = [
    ("reservoir", {"modules": {"d0": {"reservoir": {"drainage_radius": {"value": 500}}}}}),
    ("reservoir", {"d0.reservoir": {"permeability": {"value": 200, "unit": "mD"}}}),
    ("reservoir", {"degasser": {"outlet_pressure": {"value": 5, "unit": "bar(g)"}}}),
    (
        "reservoir",
        {"params": {"d0": {"reservoir": {"drainage_radius": {"value": 500}}}}, "modules": {}},
    ),
    ("reservoir", {"params": {"d0": {"nominal_flow": {"value": 250, "unit": "m3/h"}}}}),
    ("well", {"modules.d0.well": {"section_length": {"value": [2500], "unit": "m"}}}),
    ("well", {"d0": {"well": {"esp_depth": {"value": 300, "unit": "m"}}}}),
    ("well", {"injection_pump": {"efficiency": {"value": 0.7}}}),
    ("well", {"modules": {"d0": {"well_diameter": {"value": 0.2, "unit": "m"}}}}),
    ("well", {"params": {"d0": {"esp": {"stage_count": {"value": 20}}}}}),
    ("energy", {"modules.heat_pump": {"carnot_fraction": {"value": 0.5}}}),
    ("energy", {"modules": {"peak_boiler": {"efficiency": {"value": 0.9}}}}),
]
"""Patches the run refused (31 ``not_allowed``), each of the engineer's own part."""


@pytest.mark.parametrize(("discipline", "changes"), RUN_PATCHES)
def test_an_engineer_s_patch_of_its_own_part_is_never_refused(plant, discipline, changes):
    """The run's shapes go under ``params``; a path owners do not name goes by its module type."""
    placed = placed_parameters(changes, plant)
    assert set(placed) <= {"params", "modules"} and not placed.get("modules")
    check_ownership(context_of(discipline, RUN_OWNERS), placed, "patch_plant", plant)


def test_parameters_written_in_modules_or_dotted_move_under_params(plant):
    """``modules.d0.well`` and ``d0`` at the top are ``params.d0``; a module's type stays put."""
    changes = {
        "modules.d0.well": {"section_length": {"value": [1], "unit": "m"}},
        "degasser": {"outlet_pressure": {"value": 5}},
        "modules": {"heat_pump": {"type": "HeatPump", "capacity": {"value": 1, "unit": "MW"}}},
        "size": {"doublets": {"value": 2}},
    }
    assert placed_parameters(changes, plant) == {
        "modules": {"heat_pump": {"type": "HeatPump"}},
        "size": {"doublets": {"value": 2}},
        "params": {
            "d0": {"well": {"section_length": {"value": [1], "unit": "m"}}},
            "degasser": {"outlet_pressure": {"value": 5}},
            "heat_pump": {"capacity": {"value": 1, "unit": "MW"}},
        },
    }


def test_a_path_owners_do_not_name_goes_by_its_module_type(plant):
    """With no owners at all, each engineer still writes its own modules, and not another's."""
    assert default_owners("d0.reservoir.skin", plant) == {"reservoir"}
    assert default_owners("d0.esp.stage_count", plant) == {"well"}
    assert default_owners("d0.nominal_flow", plant) == {"reservoir", "well"}
    assert default_owners("filters.hot.mesh", plant) == {"reservoir"}
    assert default_owners("backup", plant) == frozenset()
    heat_pump = {"params": {"heat_pump": {"capacity": {"value": 1, "unit": "MW"}}}}
    check_ownership(context_of("energy", {}), heat_pump, "patch_plant", plant)
    with pytest.raises(ToolError, match="the energy engineer's"):
        check_ownership(context_of("well", {}), heat_pump, "patch_plant", plant)


def test_a_named_owner_decides_over_the_module_type(plant):
    """The process engineer gave the injection pump to ``well``: the energy engineer is refused."""
    patch = {"params": {"injection_pump": {"efficiency": {"value": 0.7}}}}
    with pytest.raises(ToolError, match="the well engineer's"):
        check_ownership(context_of("energy", RUN_OWNERS), patch, "patch_plant", plant)


def test_a_refusal_names_the_engineer_s_own_parts():
    """IMP-014: the not_allowed refusal lists the parts the engineer owns."""
    from geomind.tools.gemini.ownership import own_parts

    owners = {"params.d0": "reservoir_engineer", "heat_pump": "energy", "params.d0.esp": "well"}
    assert own_parts("energy", owners) == ["heat_pump"]
    assert own_parts("reservoir", owners) == ["d0"]


def test_qa_178_the_groups_of_handbook_design_0_3_own_their_modules():
    """QA-178: the injection pump is the well engineer's; treatment the reservoir engineer's."""
    from geomind.tools.gemini.ownership import type_disciplines

    assert type_disciplines("InjectionPump") == frozenset({"well"})
    for name in ("InhibitorDosing", "Blowdown", "Degasser", "BoreholeField"):
        assert type_disciplines(name) == frozenset({"reservoir"})
    assert type_disciplines("IceStorage") == frozenset({"energy"})

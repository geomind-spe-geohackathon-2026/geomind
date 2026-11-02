"""Verification over gemini's verdict: the metrics, and the domain each reason goes to."""

import functools

import pytest

from geomind.tools.gemini.verification import (
    assess,
    domain_of,
    requirement_roles,
    role_domain,
    unit_roles,
)
from tests.fixtures.stored_runs import variant_run, warm_runs


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Run the stored runs and two verdicts once, outside the timed test calls."""
    warm_runs()
    for variant in ("base", "cooling_peak"):
        assessed("hackathon_2026", variant)


@functools.cache
def assessed(name, variant):
    """Return ``assess`` of a variant's stored run, once per process; read it only."""
    return assess(*loaded(name, variant))


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


def loaded(name, variant="base"):
    """Return ``(plant, case, results)`` of a variant's stored run."""
    from geomind.tools.gemini.stored import load_run

    context, _, result = variant_run(name, variant)
    return load_run(context, result, "test")


def test_every_role_of_gemini_has_a_domain(gm):
    """The doublets are subsurface, the supplies sizing, every other role surface."""
    domains = {role: role_domain(role) for role in gm.plants.roles()}
    assert domains["doublet"] == "subsurface"
    assert domains["heating_supply"] == domains["cooling_supply"] == "sizing"
    assert {domains[role] for role in domains} == {"subsurface", "sizing", "surface"}
    assert domains["heat_pump"] == domains["boiler"] == domains["chiller"] == "surface"


def test_a_requirement_goes_to_the_domain_of_its_role():
    """The reason names its role; without it the case's requirement of that name gives it."""
    assert domain_of({"kind": "requirement", "name": "x", "role": "doublet"}, {}) == "subsurface"
    assert domain_of({"kind": "requirement", "name": "x", "role": "heat_pump"}, {}) == "surface"
    assert domain_of({"kind": "requirement", "name": "q"}, {}, {"q": "heating_supply"}) == "sizing"
    assert domain_of({"kind": "requirement", "name": "q"}, {}) == "coupled"


def test_a_reason_of_a_unit_goes_to_the_domain_of_the_role_of_that_unit():
    """Rows or bounds below a doublet are subsurface; below no unit of a known role, coupled."""
    roles = {"d0": "doublet", "heat_users": "heating_supply"}
    assert domain_of({"kind": "failed_step", "path": "d0.reservoir"}, roles) == "subsurface"
    assert domain_of({"kind": "bound", "path": "heat_users.x"}, roles) == "sizing"
    assert domain_of({"kind": "bound", "path": "boiler.x"}, roles) == "coupled"
    assert domain_of({"kind": "failed_step"}, roles) == "coupled"


def test_a_numerical_reason_is_coupled_wherever_it_lies():
    """A balance or a loop belongs to no one side."""
    assert domain_of({"kind": "numerical", "path": "d0", "role": "doublet"}, {"d0": "doublet"}) == (
        "coupled"
    )


def test_the_roles_come_from_the_requirement_checks_and_the_case(gm):
    """The report's ``unit_path`` and ``role`` give the units; the case gives the names."""
    plant, case, _ = loaded("hackathon_2026")
    roles = unit_roles(assessed("hackathon_2026", "base")["requirements"])
    assert roles["d0"] == "doublet" and roles["heat_users"] == "heating_supply"
    assert requirement_roles(case)["production_flow_range"] == "doublet"


def test_the_verdict_is_gemini_s_and_the_metrics_hold_no_report_structure(gm):
    """``feasible`` is ``gm.evaluate.verdict``; the metrics are the numbers of the report."""
    found = assessed("hackathon_2026", "cooling_peak")
    assert (
        found["feasible"]
        is gm.evaluate.verdict(*loaded("hackathon_2026", "cooling_peak"))["feasible"]
    )
    assert not {"requirements", "verdict", "services", "passed"} & set(found["metrics"])
    assert found["metrics"]["failed_steps"] == 0


def test_a_design_that_runs_on_its_case_is_feasible_and_a_hot_cooling_peak_is_not():
    """The verdict is gemini's: feasible with no reason, infeasible with the reasons it gives."""
    base = assessed("hackathon_2026", "base")
    assert base["feasible"] is True and base["reasons"] == []
    peak = assessed("hackathon_2026", "cooling_peak")
    assert peak["feasible"] is False
    assert {reason["kind"] for reason in peak["reasons"]} == {"requirement"}

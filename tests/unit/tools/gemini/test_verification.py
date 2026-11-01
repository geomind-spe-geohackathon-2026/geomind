"""Verification over gemini's report: the balances, and the domain each failure goes to."""

import pytest

from geomind.tools.gemini.verification import assess, balances, domain_of, role_domain, unit_roles
from tests.fixtures.stored_runs import variant_run, warm_runs


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Run the stored runs once, outside the event loop of a test."""
    warm_runs()


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
    domains = {role: role_domain(role) for role in gm.case.roles()}
    assert domains["doublet"] == "subsurface"
    assert domains["heating_supply"] == domains["cooling_supply"] == "sizing"
    assert {domains[role] for role in domains} == {"subsurface", "sizing", "surface"}
    assert domains["heat_pump"] == domains["boiler"] == domains["chiller"] == "surface"


def test_a_failed_check_goes_to_the_domain_of_its_role():
    """A constraint check names its role; a balance names none, so it is coupled."""
    assert domain_of({"name": "d0.x", "role": "doublet"}, {}) == "subsurface"
    assert domain_of({"name": "hp.cop", "role": "heat_pump"}, {}) == "surface"
    assert domain_of({"name": "energy_balance"}, {}) == "coupled"


def test_a_failure_group_goes_to_the_domain_of_the_unit_it_lies_in():
    """Rows that failed below a doublet are subsurface; below no constrained unit, coupled."""
    roles = {"d0": "doublet", "heat_users": "heating_supply"}
    assert domain_of({"path": "d0.reservoir", "code": "out_of_range"}, roles) == "subsurface"
    assert domain_of({"path": "heat_users", "code": "no_convergence"}, roles) == "sizing"
    assert domain_of({"path": "boiler", "code": "no_convergence"}, roles) == "coupled"


def test_the_roles_come_from_the_constraint_checks_of_the_report():
    """``unit_path`` and ``role`` of gemini's checks give the units and their roles."""
    found = assess(*loaded("hackathon_2026"))
    roles = unit_roles(found["constraints"])
    assert roles["d0"] == "doublet" and roles["heat_users"] == "heating_supply"


@pytest.mark.parametrize("name", ["hackathon_2026", "shallow_district"])
def test_the_balances_hold_on_a_design_that_runs(name):
    """The three ledgers are there and pass; the plant balance lists only what failed."""
    checks = balances(*loaded(name))
    assert [check["name"] for check in checks] == ["energy_balance", "mass_balance", "bounds"]
    assert all(check["passed"] for check in checks)


def test_a_design_that_runs_on_its_case_passes_and_a_hot_cooling_peak_does_not():
    """The verdict is gemini's report: passed with no failed constraint, balance or step."""
    assert assess(*loaded("hackathon_2026"))["passed"] is True
    assert assess(*loaded("hackathon_2026", "cooling_peak"))["passed"] is False

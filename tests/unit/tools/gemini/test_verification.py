"""Verification of a design against the brief, with gemini's checks only."""

import copy

import pytest

from geomind.tools.gemini import verification
from geomind.tools.gemini.verification import TOLERANCE, assess, challenge_limits, domain_of
from tests.fixtures.hackathon import hackathon_run


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


@pytest.fixture(scope="module")
def january(gm):
    """Return gemini's hackathon plant and its January run, which meets every limit."""
    return hackathon_run(gm)


@pytest.fixture(scope="module")
def spring(gm):
    """Return the hackathon plant and its late-March run, with heat supplied below 100 degC."""
    return hackathon_run(gm, "2027-03-20", "2027-03-31")


@pytest.fixture(scope="module")
def assessed(spring):
    """Return the assessment of the hackathon example in late March."""
    return assess(*spring)


def test_a_design_that_meets_every_limit_passes(january):
    """In January gemini's example meets the brief: nothing failed."""
    found = assess(*january)
    assert found["passed"] is True
    assert found["failures"] == []


def names(assessment):
    """Return the names of the checks, by whether they passed."""
    return {
        passed: [check["name"] for check in assessment["checks"] if check["passed"] is passed]
        for passed in (True, False)
    }


def test_the_hard_limits_follow_the_plant_s_doublets_and_grids(gm, january):
    """One limit per doublet and grid output the brief bounds, at the brief's numbers."""
    plant, _ = january
    limits = challenge_limits(plant).to_dict()["limits"]
    targets = {f"{item['pattern']}.{item['output']}" for item in limits}
    assert targets >= {
        "d0.flow",
        "d1.flow",
        "d0.brine_cooling",
        "d1.brine_cooling",
        "heat_users.supply_in.temperature",
        "heat_users.unmet_demand",
        "cool_users.supply_in.temperature",
        "cool_users.unmet_sensible",
        "cool_users.unmet_latent",
    }


def test_a_design_that_breaks_a_hard_limit_fails_with_a_check_that_names_it(assessed):
    """The example of gemini supplies heat below 100 degC on some days."""
    assert assessed["passed"] is False
    assert "heat_users.supply_in.temperature" in names(assessed)[False]


def test_the_supply_temperature_is_fixed_within_the_numerical_tolerance_only(assessed):
    """100 degC is a fixed supply: the limit is 373.15 K on both sides, widened by the tolerance."""
    check = next(c for c in assessed["checks"] if c["name"] == "heat_users.supply_in.temperature")
    low, high = check["limit"]["value"]
    assert low == pytest.approx(373.15 - TOLERANCE["temperature"], abs=1e-9)
    assert high == pytest.approx(373.15 + TOLERANCE["temperature"], abs=1e-9)


def test_the_balances_and_the_brief_s_counts_are_checks(assessed):
    """The balances of gemini, and the number of doublets and of failed days."""
    passed = names(assessed)[True]
    assert {"energy_balance", "mass_balance", "bounds", "plant energy", "plant mass"} <= set(passed)
    assert {"doublets", "failed_days", "heating_grid", "cooling_grid"} <= set(passed)


def test_every_check_keeps_gemini_s_shape(assessed):
    """Name, passed, value and limit; nothing more."""
    assert all(set(check) == {"name", "passed", "value", "limit"} for check in assessed["checks"])


def test_each_failure_names_its_domain(assessed):
    """A wrong supply temperature is a surface failure."""
    assert {"name": "heat_users.supply_in.temperature", "domain": "surface"} in assessed["failures"]
    assert all(set(item) == {"name", "domain"} for item in assessed["failures"])


@pytest.mark.parametrize(
    ("name", "domain"),
    [
        ("d0.flow", "subsurface"),
        ("d1.brine_cooling", "subsurface"),
        ("doublets", "subsurface"),
        ("d0 mass", "subsurface"),
        ("heat_users.supply_in.temperature", "surface"),
        ("cool_users.supply_in.temperature", "surface"),
        ("heat_pump energy", "surface"),
        ("heating_grid", "surface"),
        ("heat_users.unmet_demand", "sizing"),
        ("cool_users.unmet_latent", "sizing"),
        ("plant energy", "coupled"),
        ("energy_balance", "coupled"),
        ("failed_days", "coupled"),
    ],
)
def test_the_domain_of_a_check_follows_the_module_it_names(january, name, domain):
    """Doublets are subsurface, unmet demand is sizing, the whole plant is coupled."""
    plant, _ = january
    assert domain_of(name, verification.module_types(plant)) == domain


def test_what_gemini_cannot_judge_is_not_assessed_with_its_reason(gm, assessed):
    """The 330 operating days are blocked with gemini's own message; two limits wait for outputs."""
    entries = {item["id"]: item for item in assessed["not_assessed"]}
    days = entries["operating_days"]
    assert days["status"] == "BLOCKED"
    assert "330 daily steps is not decided yet" in days["reason"]
    assert entries["volume_balance"]["status"] == "NOT_ASSESSED"
    assert entries["pump_efficiency"]["status"] == "NOT_ASSESSED"
    assert entries["pump_efficiency"]["value"] == {"d0": 0.7, "d1": 0.7}


def test_a_failed_day_fails_the_failed_days_check(gm):
    """A day gemini could not run is never a passed day."""
    plant = gm.plants.example("DoubletHeatPlant")
    from geomind.tools.gemini.brief import SCHEDULE_RULES

    demand = gm.profiles.get("heating_demand").loc["2027-01-01":"2027-01-03"]
    results = gm.simulate(plant, gm.schedule(plant, demand, SCHEDULE_RULES), on_error="record")
    found = {check["name"]: check for check in assess(plant, results)["checks"]}
    assert found["failed_days"]["passed"] is False
    assert found["failed_days"]["value"] == {"value": 3, "unit": "-"}
    assert found["doublets"]["passed"] is True
    assert found["cooling_grid"]["passed"] is False
    assert found["doublet.flow"]["passed"] is None
    assert "every day failed" in found["doublet.flow"]["value"]["reason"]


def test_more_limits_add_to_the_brief_s(gm, spring):
    """A user's limit is checked beside the hard limits, never instead of them."""
    plant, results = spring
    extra = gm.checks.Limits().add("d0.brine_cooling", max="1 K").to_dict()
    found = names(assess(plant, results, copy.deepcopy(extra)))
    assert found[False].count("d0.brine_cooling") == 1
    assert "heat_users.supply_in.temperature" in found[False]

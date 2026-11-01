"""Verification of a run on its case: gemini's report, with each failure routed by domain."""

import pytest

import geomind as gd
from geomind.tools.gemini.stored import load_run
from tests.fixtures.cases import example_names
from tests.fixtures.stored_runs import variant_run, warm_runs


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Run the stored runs once, outside the event loop of a test."""
    warm_runs()


def verdict(name, variant="base"):
    """Return ``gd.verify.verify`` of a variant's stored run."""
    context, _, result = variant_run(name, variant)
    plant, case, results = load_run(context, result, "test")
    return gd.verify.verify(plant, results, case)


@example_names
def test_a_design_that_meets_its_case_passes(name):
    """Gemini's report passes, so nothing is listed as failed and the checks are given."""
    found = verdict(name)
    assert found["passed"] is True
    assert found["failures"] == []
    assert found["checks"]
    assert found["metrics"]["failed_steps"] == 0


def test_the_signature_takes_the_plant_the_results_and_the_case():
    """The case is required; there are no requirements or limits beside it."""
    import inspect

    assert list(inspect.signature(gd.verify.verify).parameters) == ["plant", "results", "case"]


def test_a_cooling_peak_the_design_cannot_meet_fails_in_sizing():
    """The cooling grid gets water above the case's 20 degC; the supply is sized, not the wells."""
    found = verdict("hackathon_2026", "cooling_peak")
    assert found["passed"] is False
    assert [item["name"] for item in found["failures"]] == ["cool_users.supply_in.temperature"]
    failure = found["failures"][0]
    assert failure["domain"] == "sizing"
    assert "degC against 20.0 degC" in failure["detail"]


def test_a_colder_reservoir_passes_because_no_constraint_limits_the_boiler():
    """Gemini passes the 25 K/km variant; the verdict is its own, with the boiler's heat shown."""
    found = verdict("hackathon_2026", "colder")
    base = verdict("hackathon_2026")
    assert found["passed"] is True
    assert found["metrics"]["boiler_heat"]["value"] > 100 * base["metrics"]["boiler_heat"]["value"]

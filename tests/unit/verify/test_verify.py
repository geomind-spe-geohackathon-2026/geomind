"""Verification of a run on its case: gemini's verdict, with each reason routed by domain."""

import copy
import functools

import pytest

import geomind as gd
from geomind.tools.gemini.stored import load_run
from tests.fixtures.cases import EXAMPLES, example_names
from tests.fixtures.stored_runs import variant_run, warm_runs


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Run the stored runs and their verdicts once, outside the timed test calls."""
    warm_runs()
    for name, variant in (*((name, "base") for name in EXAMPLES), ("hackathon_2026", "colder")):
        verdict(name, variant)
    verdict("hackathon_2026", "cooling_peak")
    broken("well_diameter", 0.001, "m")
    broken("esp.minimum_intake_pressure", 5000, "bar")


@functools.cache
def verdict(name, variant="base"):
    """Return ``gd.verify.verify`` of a variant's stored run, once per process; read it only."""
    context, _, result = variant_run(name, variant)
    plant, case, results = load_run(context, result, "test")
    return gd.verify.verify(plant, results, case)


@functools.cache
def broken(path, value, unit):
    """Return the verdict on the hackathon design with the doublet ``path`` set to ``value unit``."""
    import gemini as gm

    context, _, result = variant_run("hackathon_2026", "base")
    plant, case, _ = load_run(context, result, "test")
    data = copy.deepcopy(plant.to_dict())
    holder = data["params"]["d0"]
    *parents, leaf = path.split(".")
    for key in parents:
        holder = holder[key]
    holder[leaf] = {"value": value, "unit": unit}
    design = gm.Plant.from_dict(data)
    return gd.verify.verify(design, gm.simulate(design, case, on_error="record"), case)


@example_names
def test_a_design_that_meets_its_case_passes(name):
    """Gemini's verdict is feasible, so nothing is listed as failed and the checks are given."""
    found = verdict(name)
    assert found["passed"] is True
    assert found["failures"] == []
    assert found["checks"]
    assert found["metrics"]["failed_steps"] == 0


def test_the_signature_takes_the_plant_the_results_and_the_case():
    """The case is required; there are no requirements or limits beside it."""
    import inspect

    assert list(inspect.signature(gd.verify.verify).parameters) == ["plant", "results", "case"]


def test_a_cooling_peak_the_design_cannot_meet_fails_two_requirements_in_sizing():
    """The cooling is not delivered and its grid gets water above 20 degC: the supply is sized."""
    found = verdict("hackathon_2026", "cooling_peak")
    assert found["passed"] is False
    assert [(item["name"], item["kind"], item["domain"]) for item in found["failures"]] == [
        ("cold_delivered", "requirement", "sizing"),
        ("cooling_supply_temperature", "requirement", "sizing"),
    ]
    assert "degC against 20.0 degC" in found["failures"][1]["detail"]


def test_a_colder_reservoir_passes_because_no_requirement_limits_the_boiler():
    """Gemini passes the 25 K/km variant; the verdict is its own, with the boiler's heat shown."""
    found = verdict("hackathon_2026", "colder")
    base = verdict("hackathon_2026")
    assert found["passed"] is True
    assert found["metrics"]["boiler_heat"]["value"] > 100 * base["metrics"]["boiler_heat"]["value"]


def test_a_failed_step_fails_as_failed_step_in_the_domain_of_its_unit():
    """A well too narrow for the flow stops the pump of d0: the rows lie below a doublet."""
    found = broken("well_diameter", 0.001, "m")
    assert found["passed"] is False
    steps = [item for item in found["failures"] if item["kind"] == "failed_step"]
    assert [(item["name"], item["domain"]) for item in steps] == [
        ("d0.esp out_of_range", "subsurface")
    ]
    assert "330 failed steps" in steps[0]["detail"]


def test_an_output_past_a_limit_of_its_module_fails_as_a_bound_in_its_unit():
    """An intake pressure under the pump's minimum is a bound of the doublet, not a requirement."""
    found = broken("esp.minimum_intake_pressure", 5000, "bar")
    assert found["passed"] is False
    assert [(item["name"], item["kind"], item["domain"]) for item in found["failures"]] == [
        ("intake_pressure", "bound", "subsurface")
    ]

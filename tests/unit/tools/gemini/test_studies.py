"""The tools that list the studies of a chat and read one."""

from geomind.tools.gemini import studies
from tests.unit.tools.gemini.test_study import SHALLOW, run, started


async def test_list_studies_of_a_chat_without_studies_is_empty():
    """No study yet is an empty list."""
    context, _ = await started(SHALLOW)
    assert (await run(studies.list_studies, context, {})).output == []


async def test_read_study_of_an_unknown_key_is_unknown_name():
    """A key no tool returned says so."""
    context, _ = await started(SHALLOW)
    result = await run(studies.read_study, context, {"study": "design/start"})
    assert result.output["error"]["code"] == "unknown_name"


def test_read_study_shows_every_trial_of_an_optimisation():
    """QA-205: counts and spans over gemini's whole history, not a sample of it."""

    def trial(value, violation, doublets, chiller):
        return {
            "value": value,
            "unit": "EUR/MWh",
            "violation": violation,
            "parameters": {"doublets": {"value": doublets, "unit": "-"}, "chiller": chiller},
        }

    history = [
        trial(49.3, 0, 2, "absorption"),
        trial(52.0, 0, 3, "electric"),
        trial(48.0, 1.5, 1, "absorption"),
        trial(None, 0, 1, "absorption"),
    ]
    found = studies.trials_of(history)
    assert (found["count"], found["feasible"]) == (4, 2)
    assert found["objective"] == {"min": 49.3, "max": 52.0, "unit": "EUR/MWh"}
    assert found["parameters"]["doublets"] == {"min": 2, "max": 3, "unit": "-"}
    assert found["parameters"]["chiller"] == {"options": ["absorption", "electric"]}

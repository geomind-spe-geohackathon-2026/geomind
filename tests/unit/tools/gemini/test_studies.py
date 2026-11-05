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


def test_a_project_result_of_another_chat_is_listed_once():
    """QA-294: results with no study are listed; a study's own result is not listed twice."""
    from types import SimpleNamespace

    own = {"id": "aaa", "plant_version": 1, "case_version": 3}
    other = {"id": "bbb", "plant_version": 2, "case_version": 5, "kpis": {"lcoh": 44.1}}

    class Workspace:
        """A project with one page study and two results."""

        def project_designs(self, project_id):
            """Return the study with its result, and both results."""
            return {"plants": [], "studies": [{"id": "s1", "result": own}], "results": [other, own]}

    session = SimpleNamespace(workspace=Workspace(), artifacts={}, load_artifact=lambda _: None)
    context = SimpleNamespace(
        session=session, project="p1", problem=SimpleNamespace(case=None), messages=[]
    )
    listed = studies.list_studies.function(context)
    assert {"project_result": other} in listed
    assert sum("project_result" in item for item in listed) == 1

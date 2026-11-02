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

"""The stored references: their schemas, their listing and the error of a wrong one."""

import pytest

from geomind.tools.gemini.references import reference_schema, stored_references, unknown_reference
from geomind.tools.gemini.stored import save_design
from tests.fixtures.calls import call
from tests.fixtures.cases import case_context, example_plant, warm_gemini


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Pay for the gemini import outside the timed calls."""
    warm_gemini()


@pytest.mark.parametrize("kind", ["design", "result", "study"])
def test_the_schema_of_a_reference_has_a_pattern_and_one_example(kind):
    """The pattern accepts the example and the description shows it."""
    import re

    schema = reference_schema(kind)()
    assert re.fullmatch(schema["pattern"], schema["examples"][0])
    assert schema["examples"][0] in schema["description"]


def test_a_reference_list_and_an_optional_reference_keep_their_shape():
    """A list has the pattern on its items; an optional one also takes null."""
    assert reference_schema("design", many=True)()["items"]["pattern"].startswith("^design/")
    options = reference_schema("design", optional=True)()["anyOf"]
    assert {"type": "null"} in options


async def test_stored_references_lists_a_saved_design_once_under_its_kind():
    """A design saved twice is listed once, and no result is listed."""
    context = await case_context("shallow_district")
    plant = example_plant("shallow_district")
    reference = await save_design(context, "mine", plant)
    again = await save_design(context, "mine", plant)
    assert reference == again
    assert stored_references(context, "design") == ["design/mine"]
    assert stored_references(context, "result") == []


async def test_an_unknown_reference_lists_the_stored_ones_and_the_likely_intent():
    """The error names the form, an example, what is stored and the prefix that was missing."""
    context = await case_context("shallow_district")
    await save_design(context, "hphp2", example_plant("shallow_district"))
    error = unknown_reference(context, "design", "hphp2", "size_plant", "design")
    assert error.code == "unknown_name"
    assert error.path == "design"
    assert "stored design references: design/hphp2" in str(error)
    assert "did you mean 'design/hphp2'" in str(error)


async def test_an_unknown_reference_with_nothing_stored_says_so():
    """An empty chat gets that none is stored, not an empty list."""
    context = await case_context("shallow_district")
    error = unknown_reference(context, "result", "result/x", "read_result", "reference")
    assert "none stored yet in this chat for result" in str(error)


async def test_a_study_reference_that_is_wrong_lists_the_studies():
    """read_study on a missing study names the form and says what is stored."""
    from geomind.tools.gemini.studies import read_study

    context = await case_context("shallow_district")
    result = await call(read_study, {"study": "sized"}, context.session)
    assert result.output["error"]["code"] == "unknown_name"
    assert "study/<name>" in result.output["error"]["message"]
    assert "none stored yet in this chat for study" in result.output["error"]["message"]

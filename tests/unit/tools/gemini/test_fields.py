"""What each case field means, and the fields gemini describes nowhere."""

from geomind.tools.gemini.fields import CASE_FIELDS, ECONOMICS_FIELDS, meaning, undescribed
from geomind.tools.gemini.skeleton import key_tree

LIST_FIELDS = ("name", "on", "quantity", "unit", "over", "when", "min", "max")


def paths_of(schema):
    """Return the dotted path of every line of a schema's key tree, list fields left out."""
    paths = [line.split(":", 1)[0].replace("*", "").strip() for line in key_tree(schema)]
    return [path.removesuffix("[]") for path in paths if not path.startswith(LIST_FIELDS)]


def test_every_case_field_has_its_meaning():
    """Each key of gemini's case schema reads with a meaning; a new key fails here at once."""
    import gemini as gm

    assert [path for path in paths_of(gm.Case.schema()) if meaning(path, CASE_FIELDS) is None] == []


def test_every_economics_field_has_its_meaning():
    """Each key of gemini's economics schema reads with a meaning, a group by its prefix."""
    import gemini as gm

    schema = gm.case.Economics.schema()
    assert [path for path in paths_of(schema) if meaning(path, ECONOMICS_FIELDS) is None] == []


def test_the_fields_gemini_describes_nowhere_are_listed_for_sahand():
    """``undescribed`` lists every field marked as having no description in gemini."""
    assert {"initial_state", "demand.heating.minimum_return_temperature"} <= set(undescribed())

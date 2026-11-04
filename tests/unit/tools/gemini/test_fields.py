"""What each case field means: gemini's descriptions, with geomind's notes on the sources."""

from geomind.tools.gemini.fields import (
    CASE_NOTES,
    case_fields,
    economics_fields,
    meaning,
    schema_descriptions,
    undescribed,
)
from geomind.tools.gemini.skeleton import key_tree

LIST_FIELDS = ("name", "on", "quantity", "unit", "over", "when", "min", "max")


def paths_of(schema):
    """Return the dotted path of every line of a schema's key tree, list fields left out."""
    paths = [line.split(":", 1)[0].replace("*", "").strip() for line in key_tree(schema)]
    return [path.removesuffix("[]") for path in paths if not path.startswith(LIST_FIELDS)]


def test_every_case_field_has_its_meaning():
    """Each key of gemini's case schema reads with a meaning; a new key fails here at once."""
    import gemini as gm

    fields = case_fields()
    assert [path for path in paths_of(gm.Case.schema()) if meaning(path, fields) is None] == []


def test_every_economics_field_has_its_meaning():
    """Each key of gemini's economics schema reads with a meaning, a group by its prefix."""
    import gemini as gm

    schema = gm.case.Economics.schema()
    fields = economics_fields()
    assert [path for path in paths_of(schema) if meaning(path, fields) is None] == []


def test_a_case_field_reads_with_gemini_s_description_then_geomind_s_note():
    """Every case key has gemini 0.6.3's description (request 22): geomind adds only the source."""
    import gemini as gm

    given = schema_descriptions(gm.Case.schema())
    fields = case_fields()
    assert fields["site.ground.gradient"] == f"{given['site.ground.gradient']}; brief/report"
    assert fields["initial_state"] == given["initial_state"]
    assert "excluded" in fields["time.end"]


def test_geomind_keeps_no_meaning_gemini_gives():
    """A note is a source, or guidance gemini's description lacks; never its meaning again."""
    import gemini as gm

    given = schema_descriptions(gm.Case.schema())
    assert set(CASE_NOTES) <= set(given)
    assert [path for path, note in CASE_NOTES.items() if note in given[path]] == []


def test_an_economics_field_reads_with_gemini_s_own_description():
    """The economics read with gemini's own descriptions, the header and ``about`` too."""
    import gemini as gm

    schema = gm.case.Economics.schema()
    fields = economics_fields()
    capex = schema["properties"]["capex"]["properties"]
    assert meaning("capex.heat_exchanger", fields) == capex["heat_exchanger"]["description"]
    assert "EUR/MW/yr" in meaning("opex.fixed.boiler", fields)
    assert meaning("format", fields) == schema["properties"]["format"]["description"]


def test_describe_case_gives_gemini_s_economics_description():
    """``describe_case("economics.revenue")`` (its lines are ``keys_under``) says SDE++."""
    from geomind.tools.gemini.skeleton import keys_under

    assert any("SDE++" in line for line in keys_under("economics.revenue.subsidy"))


def test_gemini_describes_every_field():
    """``undescribed``, the list for Sahand, is empty since gemini 0.6.3 (request 22)."""
    assert undescribed() == []


def test_a_map_entry_reads_with_its_map_s_description():
    """The text ``The entry of this map for boiler.`` says nothing: the map's text covers it."""
    fields = economics_fields()
    assert "opex.fixed.boiler" not in fields and "entry of this map" not in str(fields)
    assert "entry of this map" not in str(case_fields())

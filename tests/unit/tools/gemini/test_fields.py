"""What each case field means, and the fields gemini describes nowhere."""

from geomind.tools.gemini.fields import (
    CASE_FIELDS,
    ECONOMICS_FIELDS,
    economics_fields,
    meaning,
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

    assert [path for path in paths_of(gm.Case.schema()) if meaning(path, CASE_FIELDS) is None] == []


def test_every_economics_field_has_its_meaning():
    """Each key of gemini's economics schema reads with a meaning, a group by its prefix."""
    import gemini as gm

    schema = gm.case.Economics.schema()
    fields = economics_fields()
    assert [path for path in paths_of(schema) if meaning(path, fields) is None] == []


def test_an_economics_field_reads_with_gemini_s_own_description():
    """The economics read with gemini 0.6.2's own descriptions (requests 19, 21) over geomind's."""
    import gemini as gm

    capex = gm.case.Economics.schema()["properties"]["capex"]["properties"]
    fields = economics_fields()
    assert meaning("capex.heat_exchanger", fields) == capex["heat_exchanger"]["description"]
    assert "EUR/MW/yr" in meaning("opex.fixed.boiler", fields)
    assert meaning("format", fields) == ECONOMICS_FIELDS["format"]


def test_geomind_keeps_no_economics_text_gemini_gives():
    """``ECONOMICS_FIELDS`` holds only what gemini's schema leaves undescribed."""
    import gemini as gm

    from geomind.tools.gemini.fields import schema_descriptions

    given = schema_descriptions(gm.case.Economics.schema())
    assert set(ECONOMICS_FIELDS) & set(given) == set()


def test_describe_case_gives_gemini_s_economics_description():
    """``describe_case("economics.revenue")`` (its lines are ``keys_under``) says SDE++."""
    from geomind.tools.gemini.skeleton import keys_under

    assert any("SDE++" in line for line in keys_under("economics.revenue.subsidy"))


UNDESCRIBED_IN_SCHEMA = (
    "about",
    "initial_state",
    "demand.heating.minimum_return_temperature",
    "demand.heating.maximum_return_temperature",
    "demand.cooling.minimum_return_temperature",
    "demand.cooling.maximum_return_temperature",
)
"""The case fields gemini's schema gives no description for (plan.md, gemini request 22)."""


def test_the_fields_gemini_describes_nowhere_are_listed_for_sahand():
    """``undescribed`` lists exactly the fields still marked ``(gemini: none)``."""
    marked = [path for path, text in CASE_FIELDS.items() if "(gemini: none)" in text]
    marked += [f"economics.{p}" for p, text in ECONOMICS_FIELDS.items() if "(gemini: none)" in text]
    assert undescribed() == marked


def test_the_fields_described_from_gemini_s_code_are_not_listed():
    """The seven fields taken from gemini's code are no longer on ``undescribed``'s list."""
    assert set(undescribed()).isdisjoint({*UNDESCRIBED_IN_SCHEMA, "economics.about"})


def test_each_field_without_a_schema_description_says_where_it_comes_from():
    """Each of the seven reads from gemini's code or says gemini does not use it."""
    texts = [CASE_FIELDS[path] for path in UNDESCRIBED_IN_SCHEMA] + [ECONOMICS_FIELDS["about"]]
    sources = ("from gemini's code", "gemini does not use it")
    assert [text for text in texts if not any(source in text for source in sources)] == []

"""``describe_case`` and the compact case tree: the meanings on demand, fewer tokens per call."""

from geomind.tools.gemini import describe_case
from geomind.tools.gemini.skeleton import source_tag, trees
from tests.fixtures.calls import call


def test_the_compact_tree_keeps_each_key_and_its_source_but_no_meaning():
    """The case lead's prompt carried 13.5k characters of tree on every call (Track A)."""
    full, compact = trees("case")(), trees("case_compact")()
    assert len(compact) < 0.7 * len(full)
    assert "site.reservoir.temperature: {value, unit} [derived]" in compact
    assert "site.air.temperature: {value, unit} or {file, column, unit, time_zone}" in compact
    assert (
        "undisturbed ground temperature" not in compact and "requirements.over options" in compact
    )


def test_a_meaning_gives_its_source_tag():
    """The words after the last semicolon say where a value comes from."""
    assert source_tag("brine density; brief/report") == "brief/report"
    assert source_tag("measured only; derived from the ground when unset") == "derived"
    assert source_tag("free notes (gemini: none)") is None


async def test_describe_case_gives_the_meanings_and_units_under_a_path():
    """``site.air`` gives its three keys; ``requirements`` its fields and the options."""
    keys = (await call(describe_case, {"path": "site.air"})).output["keys"]
    assert len(keys) == 3 and "outside air temperature" in keys[0] and "degC" in keys[0]
    rules = (await call(describe_case, {"path": "requirements"})).output["keys"]
    assert any(line.strip().startswith("over:") for line in rules)
    assert "requirements.over options" in rules[-1]
    capex = (await call(describe_case, {"path": "economics.capex"})).output["keys"]
    assert capex[0].startswith("capex.drilling")


async def test_an_unknown_path_names_the_parts():
    """A path the case has not answers ``unknown_name`` with the parts."""
    error = (await call(describe_case, {"path": "sight"})).output["error"]
    assert error["code"] == "unknown_name" and "site" in error["suggestions"]

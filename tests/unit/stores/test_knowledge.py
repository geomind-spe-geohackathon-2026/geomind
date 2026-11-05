"""The knowledge base: documents cut into passages, ranked by the words of a query."""

from geomind.stores.knowledge import FolderKnowledge, MemoryKnowledge, passages_of, ranked
from tests.fixtures import ROOT

TEXT = b"Drilling report\n\nThe net drilling cost was high.\n\nPumps ran well."


def test_a_document_is_cut_into_passages_with_its_citation():
    """Each passage names its document, its title and, for a PDF, its page."""
    passages = passages_of("r.md", "Title\n\nA paragraph.\n\n[page 2]\nOn a page.")
    assert [item["document"] for item in passages] == ["r.md"] * len(passages)
    assert passages[0]["title"] == "Title"
    pdf = passages_of("r.pdf", "[page 1]\nFirst page.\n\n[page 2]\nSecond page.")
    assert [item["page"] for item in pdf] == [1, 2]


def test_a_search_ranks_passages_by_the_query_s_words():
    """The passage that holds the words comes first, with a score; none for no word."""
    knowledge = MemoryKnowledge({"report.md": TEXT})
    found = knowledge.search("drilling cost")
    assert "net drilling cost" in found[0]["text"] and found[0]["score"] > 0
    assert ranked(knowledge.passages(), "", 5) == []


def test_a_table_is_cut_into_rows_each_with_its_header():
    """A CSV passage keeps the header line, so a row reads with its columns."""
    rows = "\n".join(f"item{n},{n},EUR" for n in range(400))
    passages = passages_of("c.csv", f"item,value,unit\n{rows}")
    assert len(passages) > 1 and all(
        item["text"].startswith("item,value,unit") for item in passages
    )


def test_the_folder_of_the_repository_holds_the_cost_catalogue():
    """``data/knowledge`` is the command line's knowledge base: the catalogue is a document."""
    knowledge = FolderKnowledge(ROOT / "data" / "knowledge")
    assert "data-economics.csv" in [item["name"] for item in knowledge.files()]
    assert knowledge.search("drilling")[0]["document"] == "data-economics.csv"


REFUSED_BY_GEMINI = {
    "opex-pipe-dea-2025-distribution",
    "opex-pipe-dea-2025-transmission",
    "waste-disposal-tfa-france-2022",
    "waste-density-geothermal-filter-nrg-2020",
}
"""Catalogue rows listed for reference whose unit gemini's key refuses, so they are never used:
``opex.fixed.pipe`` per MW and year (it takes %/yr only), and ``opex.variable.waste_disposal`` in
EUR/m3 or t/m3 (it takes EUR/kg; data-economics.md)."""


def test_every_catalogue_row_names_a_case_key_and_a_unit_gemini_takes():
    """Every catalogue ``path`` is a key of the case and its unit one the key takes (16, 17).

    gemini 0.6.3's catalogue names the case keys (``economics.capex.drilling``,
    ``utilities.electricity.co2_intensity``), and ``capex.pipe`` takes EUR/MW/m. A basis word
    after the unit aside; a number with no unit (a share, a GWP) is not judged here, nor a row
    with no 2015 value (USD), except a case value outside the economics (the grid's CO2, g/kWh).
    """
    import csv

    import gemini as gm

    from geomind.tools.gemini.unit_bridge import _accepted_units, _child_schema

    schemas = {"economics": gm.case.Economics.schema()}
    rows = csv.DictReader((ROOT / "data" / "knowledge" / "data-economics.csv").open())
    unknown, refused = [], []
    for row in rows:
        if not row["path"]:
            continue
        first, _, rest = row["path"].partition(".")
        node, parts = (
            (schemas[first], rest) if first in schemas else (gm.Case.schema(), row["path"])
        )
        for part in parts.split("."):
            node = _child_schema(node, part)
        if node is None:
            unknown.append(row["id"])
            continue
        unit = row["unit_2015"].split(" ")[0] or (row["unit"] if first == "utilities" else "")
        accepted = _accepted_units(node)
        if unit and accepted and unit not in accepted:
            refused.append(row["id"])
    assert unknown == [] and set(refused) == REFUSED_BY_GEMINI


def test_the_pipe_rows_per_mw_and_metre_are_usable():
    """Request 16: gemini 0.6.3 prices ``capex.pipe`` per MW and m (DEA's transmission row)."""
    import csv

    catalogue = (ROOT / "data" / "knowledge" / "data-economics.csv").open()
    rows = {row["id"]: row for row in csv.DictReader(catalogue)}
    row = rows["pipe-dea-2025-transmission-0-50mw"]
    assert (row["path"], row["unit_2015"]) == ("economics.capex.pipe", "EUR/MW/m")


def test_the_rows_gemini_0_6_2_takes_as_their_source_states_them():
    """The fixed O&M per MW and year, and the SDE++ full-load hours as ``subsidy.cap``.

    gemini 0.6.2 takes ``opex.fixed.<kind>`` per MW and year for a kind sized by a power, so the
    boiler, electric boiler and CHP rows give the source amount, not a share of an assumed capex,
    and PBL's 6000 full-load hours are the subsidy's ``cap`` in h/yr.
    """
    import csv

    catalogue = (ROOT / "data" / "knowledge" / "data-economics.csv").open()
    rows = {row["id"]: row for row in csv.DictReader(catalogue)}
    for row, amount in (
        ("opex-boiler-gas-dea-2018", "1950"),
        ("opex-boiler-electric-dea-2017", "1070"),
        ("opex-chp-gas-engine-dea-2018", "9750"),
    ):
        assert (rows[row]["value_2015"], rows[row]["unit_2015"]) == (amount, "EUR/MW/yr")
    cap = rows["sde-full-load-hours-geothermal-pbl-2026-over-20mw"]
    assert (cap["path"], cap["value_2015"], cap["unit_2015"]) == (
        "economics.revenue.subsidy.cap",
        "6000",
        "h/yr",
    )
    assert "6.000" in cap["quote"] and cap["status"] == "verified"

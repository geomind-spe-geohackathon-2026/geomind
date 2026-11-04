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
    assert "cost-sources.csv" in [item["name"] for item in knowledge.files()]
    assert knowledge.search("drilling")[0]["document"] == "cost-sources.csv"


CATALOGUE_PREFIXES = ("assumptions.finance.", "assumptions.", "economics.")
"""The prefixes of a catalogue ``path`` before the economics key, as the case lead drops them."""
REFUSED_BY_GEMINI = {
    "pipe-dea-2025-transmission-0-50mw",
    "opex-pipe-dea-2025-distribution",
    "opex-pipe-dea-2025-transmission",
}
"""Catalogue rows whose unit gemini 0.6.2's key still refuses (cost-sources.md, for Sahand)."""
NO_ECONOMICS_KEY = {"emissions.CO2.electricity"}
"""A catalogue path that is a case value, ``utilities.electricity.co2_intensity``."""


def catalogue_key(path):
    """Return the economics key of a catalogue ``path``, its prefix dropped."""
    for prefix in CATALOGUE_PREFIXES:
        if path.startswith(prefix):
            return path.removeprefix(prefix)
    return path


def test_every_catalogue_row_names_a_key_and_a_unit_gemini_takes():
    """Every catalogue row names an economics key and a unit it takes (gemini requests 16-18).

    A basis word after the unit aside; a number with no unit (a share, a GWP) is not judged here.
    """
    import csv

    import gemini as gm

    from geomind.tools.gemini.unit_bridge import _accepted_units, _child_schema

    schema = gm.case.Economics.schema()
    rows = csv.DictReader((ROOT / "data" / "knowledge" / "cost-sources.csv").open())
    unknown, refused = [], []
    for row in rows:
        key = catalogue_key(row["path"])
        if not key or key in NO_ECONOMICS_KEY:
            continue
        node = schema
        for part in key.split("."):
            node = _child_schema(node, part)
        if node is None:
            unknown.append(row["id"])
            continue
        unit, accepted = row["unit_2015"].split(" ")[0], _accepted_units(node)
        if unit and accepted and unit not in accepted:
            refused.append(row["id"])
    assert unknown == [] and set(refused) == REFUSED_BY_GEMINI

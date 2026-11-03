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

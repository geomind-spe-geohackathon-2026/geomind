"""Workspaces: plants and keyword search."""

from geomind.engine.workspace import FileWorkspace, MemoryWorkspace, search

DOCUMENTS = [
    {"id": "1", "title": "Pumps", "text": "a pump moves water"},
    {"id": "2", "title": "Heat", "text": "heat heat and a pump"},
    {"id": "3", "title": "Other", "text": "nothing here"},
]


def test_search_ranks_by_keyword_count():
    """More matches come first, and no match is left out."""
    found = search(DOCUMENTS, "heat pump")
    assert [item["id"] for item in found] == ["2", "1"]
    assert found[0]["score"] == 4


def test_memory_workspace_keeps_projects_apart():
    """Values belong to one project."""
    workspace = MemoryWorkspace({"a": "plant"}, {"a": DOCUMENTS})
    assert workspace.plant("a") == "plant" and workspace.plant("b") is None
    assert workspace.documents("b", "heat") == []


def test_file_workspace_reads_text_files(tmp_path):
    """Markdown and text files count, and other files do not."""
    folder = tmp_path / "p/documents"
    folder.mkdir(parents=True)
    (folder / "a.md").write_text("heat")
    (folder / "b.txt").write_text("heat")
    (folder / "c.bin").write_text("heat")
    found = FileWorkspace(tmp_path).documents("p", "heat")
    assert sorted(item["id"] for item in found) == ["a.md", "b.txt"]


def test_file_workspace_without_a_plant(tmp_path):
    """A project without a plant file has no plant."""
    assert FileWorkspace(tmp_path).plant("p") is None

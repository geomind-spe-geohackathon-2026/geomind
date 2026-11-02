"""Workspaces: plants, cases and keyword search."""

import json
import shutil

import pytest

from geomind.errors import UnknownNameError
from geomind.stores.casefiles import is_safe_name, named_files
from geomind.stores.workspace import FileWorkspace, MemoryWorkspace, search
from tests.fixtures.cases import (
    EXAMPLES,
    example_case,
    example_folder,
    example_names,
    example_plant_files,
)

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


@pytest.fixture(scope="module")
def projects(tmp_path_factory):
    """Return a root folder with both example projects laid out as gemini's project folders."""
    root = tmp_path_factory.mktemp("projects")
    for name in EXAMPLES:
        shutil.copytree(example_folder(name), root / name)
    return root


@example_names
def test_file_workspace_reads_a_case_and_every_file_it_names(projects, name):
    """The case is the content of ``case.json``, as written; the files include the economics."""
    data, files = FileWorkspace(projects).case(name)
    assert data == json.loads((projects / name / "case.json").read_text())
    assert set(files) == {"economics.json", "data/demand.csv"}
    assert files["economics.json"] == (projects / name / "economics.json").read_bytes()


@example_names
def test_the_file_and_memory_workspaces_agree(projects, name):
    """The memory workspace given an example holds what the file workspace reads."""
    memory = MemoryWorkspace(cases={name: example_case(name)})
    assert memory.case(name) == FileWorkspace(projects).case(name)


def test_file_workspace_reads_the_plant_file(projects):
    """The one file of ``plants/`` is a gemini plant built by ``Plant.from_dict``."""
    plant = FileWorkspace(projects).plant("shallow_district")
    file = json.loads(example_plant_files("shallow_district").popitem()[1])
    assert plant.to_dict()["type"] == file["type"]


def test_file_workspace_refuses_to_pick_among_several_plants(projects):
    """The hackathon project has six plant files, so ``plant`` names no one of them."""
    with pytest.raises(UnknownNameError, match="several plants"):
        FileWorkspace(projects).plant("hackathon_2026")


def test_file_workspace_without_a_case(tmp_path):
    """A project without a case file has no case."""
    assert FileWorkspace(tmp_path).case("p") is None


def test_file_workspace_never_reads_outside_the_project(tmp_path):
    """A name with ``..`` or an absolute path is not read."""
    (tmp_path / "secret.csv").write_text("x")
    project = tmp_path / "p"
    project.mkdir()
    case = {"demand": {"heating": {"power": {"file": "../secret.csv"}}}, "economics": "/etc/hosts"}
    (project / "case.json").write_text(json.dumps(case))
    assert FileWorkspace(tmp_path).case("p") == (case, {})


def test_memory_workspace_keeps_cases_by_project():
    """A case belongs to one project."""
    workspace = MemoryWorkspace(cases={"a": ({"time": {}}, {})})
    assert workspace.case("a") == ({"time": {}}, {})
    assert workspace.case("b") is None


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("data/demand.csv", True),
        ("economics.json", True),
        ("../x.csv", False),
        ("/etc/passwd", False),
        ("a/../b", False),
        ("a//b", False),
        ("a\\b", False),
        ("C:/x", False),
        ("", False),
    ],
)
def test_file_names_are_relative_paths_inside_the_project(name, safe):
    """Only a relative path of plain parts is a case file name."""
    assert is_safe_name(name) is safe


def test_an_economics_file_names_series_beside_it():
    """A series of ``plans/economics.json`` is read relative to that file."""
    content = json.dumps({"price": {"file": "prices.csv"}}).encode()
    files = named_files(
        {"economics": "plans/economics.json"},
        {"plans/economics.json": content, "plans/prices.csv": b"x"}.get,
    )
    assert set(files) == {"plans/economics.json", "plans/prices.csv"}

"""Workspaces: plants, cases and keyword search."""

import json
import shutil

import pytest

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
    workspace = MemoryWorkspace({"a": {"P": {"kind": "plant"}}}, {"a": DOCUMENTS})
    assert workspace.plants("a") == {"P": {"kind": "plant"}} and workspace.plants("b") == {}
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
    """A project without a plant file has no plants."""
    assert FileWorkspace(tmp_path).plants("p") == {}


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


@example_names
def test_file_workspace_reads_every_plant_file_by_its_stem(projects, name):
    """``plants`` is ``{stem: file dict}`` of ``plants/*.json``, as written."""
    plants = FileWorkspace(projects).plants(name)
    files = example_plant_files(name)
    assert plants == {
        file.removeprefix("plants/").removesuffix(".json"): json.loads(content)
        for file, content in files.items()
    }
    assert {file["kind"] for file in plants.values()} == {"plant"}


def test_the_hackathon_project_has_several_plants_and_shallow_district_one(projects):
    """A project may hold any number of plant files."""
    assert len(FileWorkspace(projects).plants("hackathon_2026")) == 6
    assert len(FileWorkspace(projects).plants("shallow_district")) == 1


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


def test_a_memory_workspace_holds_files_by_project():
    """The files keep their bytes, and an unknown file or project has none."""
    workspace = MemoryWorkspace(files={"p": {"a.csv": b"x,y\n", "b.bin": b"\x00"}})
    assert workspace.files("p") == [
        {"name": "a.csv", "size": 4, "media_type": "text/csv"},
        {"name": "b.bin", "size": 1, "media_type": "application/octet-stream"},
    ]
    assert workspace.file("p", "a.csv") == b"x,y\n"
    assert workspace.file("p", "c.csv") is None
    assert workspace.files("q") == []
    assert workspace.file("q", "a.csv") is None


def test_a_file_workspace_lists_the_files_folder(tmp_path):
    """``files/`` holds a project's files, by their path below it."""
    folder = tmp_path / "p" / "files" / "sub"
    folder.mkdir(parents=True)
    (folder.parent / "a.csv").write_text("x,y\n")
    (folder / "b.txt").write_text("text")
    workspace = FileWorkspace(tmp_path)
    assert [item["name"] for item in workspace.files("p")] == ["a.csv", "sub/b.txt"]
    assert workspace.file("p", "sub/b.txt") == b"text"
    assert workspace.file("p", "c.csv") is None
    assert workspace.files("q") == []


@pytest.mark.parametrize("name", ["../secret.txt", "/etc/passwd", "sub/../../secret.txt"])
def test_a_file_workspace_stays_in_the_files_folder(tmp_path, name):
    """A name cannot leave ``files/``."""
    (tmp_path / "p" / "files").mkdir(parents=True)
    (tmp_path / "p" / "secret.txt").write_text("secret")
    assert FileWorkspace(tmp_path).file("p", name) is None

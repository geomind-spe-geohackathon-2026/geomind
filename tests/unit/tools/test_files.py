"""The tools that read the files of a project: ``list_files`` and ``read_rag``."""

from pathlib import Path

import pytest

from geomind.stores import MemoryWorkspace
from geomind.tools import list_files, read_rag
from geomind.tools.files import span_of
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession

FILES = Path(__file__).parents[2] / "fixtures" / "files"
CSV = (FILES / "demand.csv").read_bytes()
PDF = (FILES / "requirements.pdf").read_bytes()
PROJECT_FILES = {
    "demand.csv": CSV,
    "demand.tsv": CSV.replace(b",", b"\t"),
    "note.md": b"# Note\n\nHeat is needed in winter.\n",
    "values.json": b'{"a": 1}\n',
    "requirements.pdf": PDF,
    "broken.pdf": b"%PDF-1.4 nothing else",
    "picture.png": b"\x89PNG\r\n\x1a\n\x00\x00",
    "long.txt": b"line of text\n" * 5000,
}


def session_with(files=PROJECT_FILES):
    """Return a session whose project holds ``files``."""
    session = StubSession()
    session.workspace = MemoryWorkspace(files={"p": files})
    return session


class NoFiles:
    """A workspace of an older backend: it has no ``files``."""

    def plants(self, project_id):
        """Return no plants."""
        return {}


async def read(name, **options):
    """Return the output of ``read_rag`` on the project's files."""
    tool_input = {"name": name, **options}
    return (await call(read_rag, tool_input, session_with(), "p")).output


async def test_list_files_gives_name_size_and_media_type():
    """Each file is listed with the shape of the Workspace contract, by name."""
    files = (await call(list_files, {}, session_with(), "p")).output["files"]
    assert [item["name"] for item in files] == sorted(PROJECT_FILES)
    assert {"name": "demand.csv", "size": len(CSV), "media_type": "text/csv"} in files


async def test_without_a_project_the_tools_are_not_allowed():
    """A chat without a project has no files to read."""
    assert (await call(list_files, {})).output["error"]["code"] == "not_allowed"
    result = await call(read_rag, {"name": "a.csv"})
    assert result.output["error"]["code"] == "not_allowed"


@pytest.mark.parametrize("tool, tool_input", [(list_files, {}), (read_rag, {"name": "a.csv"})])
async def test_a_workspace_without_files_says_so(tool, tool_input):
    """A backend that has not added the methods gets a clear code, not a crash."""
    session = StubSession()
    session.workspace = NoFiles()
    assert (await call(tool, tool_input, session, "p")).output["error"]["code"] == (
        "files_unavailable"
    )


async def test_a_csv_comes_with_its_header_rows_and_first_rows():
    """The model sees the shape of the table without reading all of it."""
    output = await read("demand.csv")
    assert output["table"]["columns"] == ["time", "heat_mw"]
    assert output["table"]["rows"] == 14
    assert output["table"]["first_rows"][0] == ["2030-01-01T00:00:00Z", "5"]
    assert output["text"].startswith("time,heat_mw\n")


async def test_a_tsv_is_a_table_too():
    """Tabs separate the columns of a ``.tsv``."""
    assert (await read("demand.tsv"))["table"]["columns"] == ["time", "heat_mw"]


@pytest.mark.parametrize(
    "name, text", [("note.md", "# Note"), ("values.json", '{"a": 1}'), ("long.txt", "line")]
)
async def test_text_files_read_as_text(name, text):
    """Markdown, JSON and plain text come back as they are, without a table."""
    output = await read(name)
    assert output["text"].startswith(text)
    assert "table" not in output


async def test_a_pdf_reads_as_text_with_page_markers():
    """Each page's text follows its marker."""
    text = (await read("requirements.pdf"))["text"]
    assert "[page 1]" in text and "[page 2]" in text
    assert text.index("Supply temperature") < text.index("[page 2]")
    assert text.index("[page 2]") < text.index("Return temperature")


@pytest.mark.parametrize("name", ["picture.png", "broken.pdf"])
async def test_a_file_that_is_not_text_says_so(name):
    """The model learns it cannot read the file, and which one."""
    error = (await read(name))["error"]
    assert error["code"] == "not_text"
    assert error["path"] == "name"
    assert name in error["message"]


async def test_an_unknown_file_lists_the_project_s_files():
    """A wrong name teaches the right ones."""
    error = (await read("demnad.csv"))["error"]
    assert error["code"] == "unknown_name"
    assert "demand.csv" in error["message"]
    assert "demand.csv" in error["suggestions"]


async def test_a_long_file_is_paged():
    """``next`` is where the following page starts, and the pages join into the file."""
    first = await read("long.txt", length=1300)
    second = await read("long.txt", start=first["next"], length=1300)
    assert first["start"] == 0 and first["total"] == len(PROJECT_FILES["long.txt"])
    assert second["start"] == 1300
    assert first["text"] + second["text"] == PROJECT_FILES["long.txt"].decode()[:2600]
    last = await read("long.txt", start=first["total"] - 5)
    assert last["next"] is None


async def test_a_page_is_bounded_without_a_length():
    """A call without ``length`` cannot pull a whole long file into the context."""
    files = {"huge.txt": b"x" * 200_000}
    output = (await call(read_rag, {"name": "huge.txt"}, session_with(files), "p")).output
    assert output["next"] == len(output["text"]) < 40_000


async def test_a_negative_start_is_refused():
    """The error names the argument."""
    assert (await read("note.md", start=-1))["error"]["path"] == "start"


async def test_a_long_read_is_stored_by_reference():
    """A read over the store limit is kept as an artifact, so old reads need not stay whole."""
    session = session_with()
    result = await call(read_rag, {"name": "long.txt"}, session, "p")
    assert result.reference is not None and len(result.output["text"]) == 20000
    assert session.artifacts[result.reference]["text"] == result.output["text"]


def test_the_name_argument_has_a_pattern_and_an_example():
    """The schema teaches the form of a name, as the reference arguments do."""
    schema = read_rag.schema()["input_schema"]["properties"]["name"]
    assert schema["pattern"] and schema["examples"] == ["demand.csv"]


async def test_a_csv_of_times_gives_the_case_span_with_an_exclusive_end():
    """The case's time is copied from the file: the agent works out no date (#64)."""
    table = (await read("demand.csv"))["table"]
    assert table["last_row"] == ["2030-01-14T00:00:00Z", "6"]
    assert table["span"] == {
        "start": "2030-01-01T00:00:00Z",
        "end": "2030-01-15T00:00:00Z",
        "step": {"value": 1, "unit": "d"},
    }


@pytest.mark.parametrize(
    "rows, span",
    [
        (
            [["2027-01-01", "1"], ["2027-01-02", "2"], ["2027-12-31", "3"]],
            None,
        ),
        (
            [["2027-12-30", "1"], ["2027-12-31", "2"]],
            {"start": "2027-12-30", "end": "2028-01-01", "step": {"value": 1, "unit": "d"}},
        ),
        (
            [["2030-01-01T00:00:00Z", "1"], ["2030-01-01T00:15:00Z", "2"]],
            {
                "start": "2030-01-01T00:00:00Z",
                "end": "2030-01-01T00:30:00Z",
                "step": {"value": 15, "unit": "min"},
            },
        ),
        ([["a", "1"], ["b", "2"]], None),
    ],
)
def test_the_span_is_one_step_past_the_last_row_or_none(rows, span):
    """Uneven steps or a column that is not times give no span."""
    assert span_of(rows) == span


async def test_columns_read_only_those_columns_of_a_table():
    """A wide cost table read by its id and price costs a third of the tokens (Track A)."""
    output = await read("demand.csv", columns=["heat_mw"])
    assert output["text"].startswith("heat_mw\n5\n") and output["columns"] == ["heat_mw"]
    assert output["name"] == "demand.csv" and output["table"]["columns"] == ["heat_mw"]


async def test_unknown_columns_name_the_table_s_columns():
    """A column the table has not is ``unknown_name`` with the header."""
    error = (await read("demand.csv", columns=["heat"]))["error"]
    assert error["code"] == "unknown_name" and "heat_mw" in error["message"]
    assert "heat_mw" in error["suggestions"]


async def test_columns_of_a_file_that_is_no_table_are_refused():
    """Only a CSV or TSV has columns."""
    assert "no CSV or TSV" in (await read("note.md", columns=["a"]))["error"]["message"]


async def test_a_page_this_run_read_is_in_its_conversation():
    """The run's own stored page stays whole for the run: the note says so, not ``read_stored``."""
    session = session_with()
    await call(read_rag, {"name": "demand.csv"}, session, "p")
    session.documents_read["demand.csv"][0]["reference"] = "stored"
    again = (await call(read_rag, {"name": "demand.csv"}, session, "p")).output
    assert again["note"].startswith("already read in this run: its text is in the conversation")

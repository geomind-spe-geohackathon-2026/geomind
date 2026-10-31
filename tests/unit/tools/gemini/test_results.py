"""The tools over a project's results and documents."""

import pytest

from geomind.engine import Context
from geomind.errors import ToolError
from geomind.stores import MemoryWorkspace
from geomind.tools import read_result, search_documents


class Session:
    """The part of a run these tools reach."""

    def __init__(self, workspace=None):
        """Hold one stored result."""
        self.workspace = workspace
        power = {"unit": "W", "values": [1.0, 2.0, 3.0]}
        flow = {"unit": "m3/h", "values": [None, None], "time": ["t0", "t1"]}
        self.stored = {"r1": {"plant.esp": {"power": power}, "plant.well": {"flow": flow}}}

    def load_artifact(self, key):
        """Return a stored result, or ``None``."""
        return self.stored.get(key)


def context(workspace=None, project="p1"):
    """Return a context inside a stand-in run."""
    return Context(project=project, session=Session(workspace))


def test_read_result_returns_the_whole_series_with_its_unit():
    """Without a range, every sample."""
    output = read_result.function(context(), "r1", "plant.esp", "power")
    assert output == {"value": [1.0, 2.0, 3.0], "unit": "W"}


def test_read_result_returns_a_slice():
    """``start`` and ``end`` are sample positions."""
    output = read_result.function(context(), "r1", "plant.esp", "power", start=1, end=2)
    assert output == {"value": [2.0], "unit": "W"}


def test_read_result_keeps_the_stored_times():
    """A stored series with times is gemini's series Value."""
    output = read_result.function(context(), "r1", "plant.well", "flow", start=1)
    assert output == {"time": ["t1"], "value": [None], "unit": "m3/h"}


def test_read_result_without_a_path_summarises_the_result():
    """Min, max and mean of every series, each a Value."""
    output = read_result.function(context(), "r1")
    assert output["plant.esp"]["power"] == {
        "min": {"value": 1.0, "unit": "W"},
        "max": {"value": 3.0, "unit": "W"},
        "mean": {"value": 2.0, "unit": "W"},
    }


def test_read_result_with_a_path_summarises_that_path():
    """Only the module asked for."""
    assert set(read_result.function(context(), "r1", "plant.esp")) == {"plant.esp"}


def test_a_series_without_numbers_has_null_values_with_a_reason():
    """A null Value says why."""
    output = read_result.function(context(), "r1", "plant.well")
    assert output["plant.well"]["flow"]["mean"]["value"] is None
    assert output["plant.well"]["flow"]["mean"]["reason"]


def test_a_field_needs_a_path():
    """The model is told which input is missing."""
    with pytest.raises(ToolError, match="expected a path") as caught:
        read_result.function(context(), "r1", field="power")
    assert caught.value.path == "path"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("r9", "plant.esp", "power"), "expected a stored result"),
        (("r1", "plant.es", "power"), "did you mean 'plant.esp'"),
        (("r1", "plant.esp", "powers"), "did you mean 'power'"),
    ],
)
def test_a_wrong_name_tells_the_model_what_exists(arguments, message):
    """Each mistake is an error the model can fix."""
    with pytest.raises(ToolError, match=message) as caught:
        read_result.function(context(), *arguments)
    assert caught.value.code == "unknown_name"


def test_search_documents_searches_the_project():
    """The workspace of the run answers."""
    documents = {"p1": [{"id": "a", "title": "Pumps", "text": "the pump runs at 50 Hz"}]}
    output = search_documents.function(context(MemoryWorkspace(documents=documents)), "pump")
    assert output[0]["id"] == "a"


@pytest.mark.parametrize("options", [{"workspace": None}, {"project": None}])
def test_search_documents_needs_a_project(options):
    """A run without one gets an error result, not a crash."""
    arguments = {"workspace": MemoryWorkspace(), "project": "p1", **options}
    with pytest.raises(ToolError, match="no project"):
        search_documents.function(context(**arguments), "pump")


def test_both_only_read():
    """Reading needs no approval, and a replay reads again."""
    assert (read_result.effect, search_documents.effect) == ("read", "read")

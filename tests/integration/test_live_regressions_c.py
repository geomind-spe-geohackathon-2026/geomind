"""What the third live run (0.4.19, run 9bc9e7b7) got wrong, replayed offline from its calls.

NOTE: ``tests/fixtures/live/recording_c.jsonl`` is that run's recording, model moves only.
"""

import json
from pathlib import Path

from geomind.tools import read_document
from geomind.tools.gemini.case import set_case
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession

LIVE = Path(__file__).parents[1] / "fixtures" / "live"
RECORDED = [json.loads(line) for line in (LIVE / "recording_c.jsonl").read_text().splitlines()]
FILES = {path.name: path.read_bytes() for path in (LIVE / "files").iterdir()}
HEATING = "GEMINI_Heating_Demand_Daily_2027.csv"


def recorded(index, tool):
    """Return the input of the first call of ``tool`` in completion ``index`` of the recording."""
    return next(item["input"] for item in RECORDED[index]["tool_calls"] if item["name"] == tool)


def session_with_files():
    """Return a session whose project ``p`` holds the run's attached files."""
    from geomind.stores import MemoryWorkspace

    session = StubSession()
    session.workspace = MemoryWorkspace(files={"p": FILES})
    return session


async def case_error(index):
    """Return the error ``set_case`` gives the recorded call of completion ``index``."""
    output = (await call(set_case, recorded(index, "set_case"), session_with_files(), "p")).output
    return output["error"]


async def test_a_wrong_unit_beside_missing_values_keeps_its_code_and_path():
    """The run sent ``'day'`` with values missing: it came back as ``case_incomplete``."""
    error = await case_error(27)
    assert (error["code"], error["path"]) == ("invalid_unit", "time.step.unit")
    assert "time.step = {'value': 1, 'unit': 'd'}" in error["suggestions"]
    missing = [item for item in error["suggestions"] if item.startswith("case_incomplete:")]
    assert len(missing) == 1 and "demand.heating.power" in missing[0]


async def test_requirements_of_another_shape_get_one_suggestion_of_the_right_shape():
    """Eighteen ``requirements[i].on`` and ``.quantity`` paths become one shape from the schema."""
    error = await case_error(27)
    assert not any(item.startswith("requirements[") for item in error["suggestions"])
    shapes = [item for item in error["suggestions"] if item.startswith("requirements=")]
    assert len(shapes) == 1 and "doublet" in shapes[0] and "quantity" in shapes[0]


async def test_no_path_is_repeated_in_a_message():
    """The text ``time.step.unit: time.step.unit: unit = ...`` of gemini names the path once."""
    error = await case_error(27)
    assert "time.step.unit: time.step.unit" not in error["message"]


async def test_the_same_error_on_every_row_is_one_line_per_file():
    """730 problems (365 rows of two files) without an offset: two summarised lines."""
    error = await case_error(85)
    assert (error["code"], error["path"]) == ("invalid_value", "demand.heating.power.file")
    assert error["message"].count("has no offset") == 2
    assert "row 1 time = '2027-01-01'" in error["message"]
    assert "365 rows" in error["message"] and "rows 1 to 365" in error["message"]
    assert len(error["message"]) < 1500


async def test_times_without_an_offset_suggest_the_call_with_a_time_zone():
    """The suggestion is the retry with ``time_zone`` on each series, the zone left to the model."""
    error = await case_error(85)
    [retry] = [item for item in error["suggestions"] if "time_zone" in item]
    assert retry.startswith("set_case(changes=")
    assert "'time_zone': '<IANA zone of time.start>'" in retry
    assert retry.count("time_zone") == 2 and "assumption" in retry


async def test_a_date_only_csv_is_read_with_a_time_zone():
    """The recorded call with ``time_zone`` on both series is accepted; no zone is geomind's."""
    tool_input = recorded(85, "set_case")
    for series in ("heating", "cooling"):
        tool_input["changes"]["demand"][series]["power"]["time_zone"] = "UTC"
    output = (await call(set_case, tool_input, session_with_files(), "p")).output
    power = output["case"]["demand"]["heating"]["power"]
    assert "error" not in output and power["time_zone"] == "UTC"


async def test_a_forced_read_of_a_document_read_whole_is_a_note():
    """The run read the whole PDF, then 60 times again with ``force=true``."""
    session = session_with_files()
    whole = (await call(read_document, {"name": HEATING}, session, "p")).output
    assert whole["next"] is None
    again = (await call(read_document, {"name": HEATING, "force": True}, session, "p")).output
    assert "text" not in again and again["already_read"]
    assert "already read" in again["note"]


async def test_a_later_round_sees_what_an_earlier_round_read():
    """Each designer round is a nested run; the reads of the tree are one memory."""
    root = session_with_files()
    child = session_with_files()
    child.root_session = root
    child.state.run_id = "r2"
    first = (await call(read_document, {"name": HEATING}, root, "p")).output
    reference = next(iter(root.artifacts), None)
    if reference is None:
        root.artifacts["stored"] = first
        root.documents_read[HEATING][0]["reference"] = "stored"
    child.artifacts = root.artifacts
    again = (await call(read_document, {"name": HEATING}, child, "p")).output
    assert "text" not in again and again["already_read"][0]["reference"]


async def test_a_short_read_of_another_round_is_read_again():
    """A result that stayed in another run's conversation is not in this one: it is read."""
    root = session_with_files()
    child = session_with_files()
    child.root_session = root
    child.state.run_id = "r2"
    await call(read_document, {"name": HEATING, "length": 100}, root, "p")
    root.documents_read[HEATING][0]["reference"] = None
    again = (await call(read_document, {"name": HEATING, "length": 100}, child, "p")).output
    assert again["text"]

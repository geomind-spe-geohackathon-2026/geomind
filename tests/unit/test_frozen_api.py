"""The frozen interfaces: the live package against its snapshots and schemas.

A difference here means a frozen interface changed. What to do is in ``HOW_TO_CHANGE``.
"""

import json
import re

import pytest
from pydantic import TypeAdapter

import geomind as gd
from evals.tasks_format import Task
from geomind.context import ProblemState
from geomind.engine import Engine
from geomind.providers import FakeLLM
from geomind.types import Answer, Request, ToolErrorOutput
from geomind.types.events import EVENT_CLASSES, StateChanged, event_from_dict
from geomind.types.runlog import RunLogDocument
from scripts import snapshot_api
from tests.fixtures import ROOT
from tests.fixtures.runs import Worker, call, context, says, uses

SNAPSHOTS = ROOT / "tests/unit/snapshots"
SCHEMAS = ROOT / "geomind/schemas"
SAMPLES = SCHEMAS / "samples"
HOW_TO_CHANGE = """
A frozen interface changed, see .claude/docs/api.md. In the same commit:
1. raise gd.__version__ in geomind/__init__.py and pyproject.toml (a breaking change raises the
   minor version);
2. run python scripts/snapshot_api.py (--allow-same-version only for an additive change, and the
   changelog says which);
3. add a docs/CHANGELOG.md entry;
4. tell Sahand if docs/contracts.md is affected.
"""


def differences(recorded, live, where):
    """Return one line per item that differs between two JSON values."""
    if not (isinstance(recorded, dict) and isinstance(live, dict)):
        return [] if recorded == live else [f"{where}: was {recorded!r}, now {live!r}"]
    lines = []
    for name in sorted(set(recorded) | set(live)):
        if name not in live:
            lines.append(f"{where}.{name}: removed")
        elif name not in recorded:
            lines.append(f"{where}.{name}: added")
        else:
            lines += differences(recorded[name], live[name], f"{where}.{name}")
    return lines


def jsonable(data):
    """Return the value as it reads back from its file."""
    return json.loads(snapshot_api.render(data))


def read_json(path):
    """Return one JSON file."""
    return json.loads(path.read_text())


@pytest.mark.parametrize("name", snapshot_api.snapshot_documents())
def test_the_snapshot_matches_the_package(name):
    """Every frozen item is as recorded; a failure names the item."""
    live = jsonable(snapshot_api.snapshot_documents()[name])
    lines = differences(read_json(SNAPSHOTS / name), live, name)
    assert not lines, "\n".join([*lines, HOW_TO_CHANGE])


@pytest.mark.parametrize("name", snapshot_api.schema_documents())
def test_the_schema_file_equals_the_generated_one(name):
    """A schema is generated from the model that defines it, never edited."""
    live = jsonable(snapshot_api.schema_documents()[name])
    lines = differences(read_json(SCHEMAS / name), live, name)
    assert not lines, "\n".join([*lines, HOW_TO_CHANGE])


def test_the_tool_table_matches_the_snapshot():
    """Every row of the catalogue in ``tools.md`` has its tool's effect, and none is missing."""
    text = (ROOT / ".claude/docs/tools.md").read_text()
    rows = dict(re.findall(r"^\| `(\w+)` \| `\w+\.py` \| `(\w+)` \|", text, re.MULTILINE))
    tools = read_json(SNAPSHOTS / "tools.json")["items"]
    assert rows == {name: tools[name]["effect"] for name in gd.tools.gemini.__all__}
    assert [name for name in tools if f"`{name}" not in text] == []


def test_differences_name_the_item():
    """A change reads as a path, with what happened to it."""
    recorded = {"tools": {"simulate": {"effect": "compute"}, "gone": 1}}
    live = {"tools": {"simulate": {"effect": "write"}, "new": 1}}
    assert differences(recorded, live, "file") == [
        "file.tools.gone: removed",
        "file.tools.new: added",
        "file.tools.simulate.effect: was 'compute', now 'write'",
    ]


def test_the_script_refuses_a_change_at_the_same_version(tmp_path):
    """A snapshot of this version stays, and the message says what to do."""
    path = tmp_path / "api.json"
    path.write_text(json.dumps({"version": gd.__version__}))
    refusal = snapshot_api.write_files({path: "new"}, path, allow_same_version=False)
    assert "raise gd.__version__" in refusal and "--allow-same-version" in refusal
    assert path.read_text() != "new"


def test_the_flag_writes_at_the_same_version(tmp_path):
    """An additive change goes through."""
    path = tmp_path / "api.json"
    path.write_text(json.dumps({"version": gd.__version__}))
    assert snapshot_api.write_files({path: "new"}, path, allow_same_version=True) is None
    assert path.read_text() == "new"


def test_another_version_may_be_overwritten(tmp_path):
    """Raising the version is the normal way."""
    path = tmp_path / "api.json"
    path.write_text(json.dumps({"version": "0.0.1"}))
    assert snapshot_api.write_files({path: "new"}, path, allow_same_version=False) is None


def test_unchanged_files_need_no_flag(tmp_path):
    """Running the script twice is safe."""
    path = tmp_path / "api.json"
    text = json.dumps({"version": gd.__version__})
    path.write_text(text)
    assert snapshot_api.write_files({path: text}, path, allow_same_version=False) is None


def test_every_public_event_has_a_sample_that_loads_and_fits_its_schema():
    """Each sample rebuilds through ``event_from_dict``, and its ``data()`` fits the schema."""
    schemas = read_json(SCHEMAS / "events.json")["events"]
    samples = read_json(SAMPLES / "events.json")
    assert set(samples) == set(schemas)
    assert set(schemas) == {name for name, kind in EVENT_CLASSES.items() if kind.is_public}
    for name, sample in samples.items():
        keys = set(event_from_dict(sample).data())
        assert keys <= set(schemas[name]["properties"]) and set(schemas[name]["required"]) <= keys


def test_the_problem_state_sample_loads():
    """Through the real model."""
    assert ProblemState.model_validate(read_json(SAMPLES / "problem_state.json")).version == 2


def test_the_state_changed_sample_loads():
    """Through the real event, which applies the rules of the patch subset."""
    assert StateChanged(run_id="r", **read_json(SAMPLES / "state_changed.json")).version == 4


def test_the_request_sample_loads():
    """Through the real model."""
    assert Request.model_validate(read_json(SAMPLES / "request.json")).kind == "question"


def test_the_answer_samples_load():
    """One approval, one refusal and one reply."""
    adapter = TypeAdapter(Answer)
    assert len([adapter.validate_python(item) for item in read_json(SAMPLES / "answer.json")]) == 3


def test_the_runlog_sample_loads():
    """Through the real model."""
    assert RunLogDocument.model_validate(read_json(SAMPLES / "runlog.json")).run.id == "run-1"


def test_the_tool_error_sample_loads():
    """Through the real model."""
    assert ToolErrorOutput.model_validate(read_json(SAMPLES / "tool_error.json")).error.path


def test_the_eval_task_sample_loads():
    """Through the real model."""
    assert len(Task.model_validate(read_json(SAMPLES / "eval_task.json")).criteria) == 4


async def test_a_real_run_log_fits_its_schema():
    """The model of ``runlog.json`` is what ``gd.runlog`` builds, an error result included."""
    engine = Engine(llm=FakeLLM([uses(call("lookup", key=1)), says()]))
    start = context()
    await gd.loops.ToolLoop(Worker()).run(engine, start)
    log = gd.runlog(engine.store.load_events(start.run_id))
    assert log["steps"][0]["tool_calls"][0]["error"] is True
    RunLogDocument.model_validate(log)

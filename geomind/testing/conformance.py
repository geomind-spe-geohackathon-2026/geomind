"""Plain functions that exercise a protocol and the round trips geomind relies on.

Each raises ``AssertionError`` with a clear message. geomind's own tests run them against the memory
and file implementations; the backend runs them against its own.
"""

from geomind.stores.casefiles import case_files, is_safe_name
from geomind.types import Message
from geomind.types.events import StepStarted, TextDelta

RUN = "conformance-run"
OTHER_RUN = "conformance-other-run"
CHAT = "conformance-chat"
MISSING = "conformance-missing"


def _expect(is_true, message):
    """Raise ``AssertionError`` when a check fails."""
    if not is_true:
        raise AssertionError(f"conformance: {message}")


def _check_event_order(store):
    """Save events; ``load_events`` returns them equal and in sequence order."""
    events = [
        StepStarted(run_id=RUN, sequence=1, index=1),
        TextDelta(run_id=RUN, sequence=2, index=1, text="hello"),
        StepStarted(run_id=RUN, sequence=3, index=2),
    ]
    for event in events:
        store.save_event(RUN, event)
    _expect(hasattr(store, "load_events"), "a RunStore must have load_events")
    _expect(store.load_events(RUN) == events, "load_events must return events in sequence order")
    _expect(store.load_events(MISSING) == [], "load_events of an unknown run must be empty")


def _check_history(store, seed_history):
    """Check that history is oldest first and an unknown chat has none."""
    _expect(store.load_history(MISSING) == [], "the history of an unknown chat must be empty")
    if seed_history is None:
        return
    messages = [
        Message(role="user", content="first"),
        Message(role="assistant", content="second"),
        Message(role="user", content="third"),
    ]
    seed_history(store, CHAT, messages)
    loaded = store.load_history(CHAT)
    _expect(loaded == messages, "load_history must return Message records, oldest first")


def _check_state(store):
    """Check that a state round-trips, is replaced, and is ``None`` when missing."""
    _expect(store.load_state(MISSING) is None, "a missing state must load as None")
    store.save_state(CHAT, {"goal": "heat"})
    _expect(store.load_state(CHAT) == {"goal": "heat"}, "a state must round-trip as saved")
    store.save_state(CHAT, {"goal": "cold"})
    _expect(store.load_state(CHAT) == {"goal": "cold"}, "a new state must replace the old one")


def _check_artifacts(store):
    """Check that bytes and JSON round-trip by run, and a missing artifact is ``None``."""
    _expect(store.load_artifact(RUN, MISSING) is None, "a missing artifact must load as None")
    store.save_artifact(RUN, "bytes", b"\x00\x01")
    store.save_artifact(RUN, "json", {"values": [1, 2]})
    _expect(store.load_artifact(RUN, "bytes") == b"\x00\x01", "bytes must round-trip")
    _expect(store.load_artifact(RUN, "json") == {"values": [1, 2]}, "JSON must round-trip")
    _expect(store.load_artifact(OTHER_RUN, "json") is None, "artifacts must belong to one run")
    store.save_artifact(RUN, "design/conformance", {"name": "doublet"})
    store.save_artifact(RUN, "result/conformance", {"plant": {}})
    store.save_artifact(RUN, "case/data/conformance.csv", b"time,x\n1,2\n")
    _expect(
        store.load_artifact(RUN, "design/conformance") == {"name": "doublet"},
        "a design/<name> key must round-trip",
    )
    _expect(
        store.load_artifact(RUN, "result/conformance") == {"plant": {}},
        "a result/<id> key must round-trip",
    )
    _expect(
        store.load_artifact(RUN, "case/data/conformance.csv") == b"time,x\n1,2\n",
        "a case/<file name> key, a path such as data/x.csv, must round-trip its bytes",
    )


def check_run_store(factory, seed_history=None):
    """Check a ``RunStore``; ``factory()`` returns a fresh store.

    The contract has no way to write history, so give ``seed_history(store, chat_id, messages)`` to
    check its order.
    """
    _check_event_order(factory())
    _check_history(factory(), seed_history)
    _check_state(factory())
    _check_artifacts(factory())


def _check_case(workspace, project, missing_project):
    """Check that the project's case is ``(dict, files)`` with every file it names."""
    found = workspace.case(project)
    _expect(found is not None, "the project's case must load")
    data, files = found
    _expect(isinstance(data, dict) and "time" in data, "a case must be the dict of a case.json")
    _expect(
        isinstance(files, dict) and all(isinstance(item, bytes) for item in files.values()),
        "the files of a case must be {name: bytes}",
    )
    _expect(all(map(is_safe_name, files)), "a case file name must be a relative path inside it")
    missing = [name for name in case_files(data) if name not in files]
    _expect(not missing, f"the files must hold every file the case names; missing {missing}")
    _expect(workspace.case(missing_project) is None, "an unknown project must have no case")


def check_workspace(factory, *, project, query, missing_project="conformance-missing"):
    """Check a ``Workspace``; ``factory()`` holds a plant, a case and a document for ``query``."""
    workspace = factory()
    _expect(workspace.plant(project) is not None, "the project's plant must load")
    _expect(workspace.plant(missing_project) is None, "an unknown project must have no plant")
    _check_case(workspace, project, missing_project)
    found = workspace.documents(project, query)
    _expect(found, "documents must find the query")
    for document in found:
        _expect(
            set(document) == {"id", "title", "text", "score"},
            "a document must have id, title, text and score",
        )
    scores = [document["score"] for document in found]
    _expect(scores == sorted(scores, reverse=True), "documents must come best first")
    _expect(workspace.documents(missing_project, query) == [], "an unknown project has none")

"""The problem state: the contract's patches, validation and rendering."""

import json

import pytest

from geomind.context import ProblemState, apply_changes, render
from geomind.errors import StateError
from tests.fixtures.cases import example_case, example_names

R1 = {
    "id": "R1",
    "text": "Cover the load",
    "case_requirement": "heat_delivered",
}
A1 = {"id": "A1", "text": "Inlet temperature", "value": 80, "source": "user"}


def with_items():
    """Return a state with one requirement and one assumption."""
    return apply_changes(
        ProblemState(),
        [
            {"op": "add", "path": "/requirements/-", "value": R1},
            {"op": "add", "path": "/assumptions/-", "value": A1},
        ],
    )


def test_a_new_state_is_empty_at_version_zero():
    """Every key of the contract starts empty."""
    state = ProblemState()
    assert (state.version, state.goal, state.requirements, state.design) == (0, "", (), {})


def test_changes_make_a_new_state_one_version_up():
    """The old state stays as it was."""
    state = ProblemState()
    changed = apply_changes(state, [{"op": "replace", "path": "/goal", "value": "Size the pump"}])
    assert (changed.version, changed.goal) == (1, "Size the pump")
    assert (state.version, state.goal) == (0, "")


def test_the_example_of_the_contract_applies():
    """Add, replace and remove, by id."""
    state = apply_changes(
        with_items(), [{"op": "add", "path": "/questions/-", "value": {"id": "Q2", "text": "Why?"}}]
    )
    changed = apply_changes(
        state,
        [
            {"op": "add", "path": "/requirements/-", "value": {**R1, "id": "R3"}},
            {"op": "replace", "path": "/assumptions/A1/confirmed", "value": True},
            {"op": "remove", "path": "/questions/Q2"},
        ],
    )
    assert [item.id for item in changed.requirements] == ["R1", "R3"]
    assert changed.assumptions[0].confirmed is True
    assert changed.questions == ()
    assert changed.version == 3


def test_an_item_is_replaced_and_removed_by_id():
    """The id in the path selects the item, wherever it sits."""
    replaced = apply_changes(
        with_items(), [{"op": "replace", "path": "/requirements/R1", "value": {**R1, "text": "x"}}]
    )
    assert replaced.requirements[0].text == "x"
    assert (
        apply_changes(replaced, [{"op": "remove", "path": "/requirements/R1"}]).requirements == ()
    )


def test_free_form_keys_take_add_replace_and_remove():
    """``design`` and ``verification`` are objects; an escaped key is one token."""
    state = apply_changes(ProblemState(), [{"op": "add", "path": "/design/a~1b", "value": 1}])
    assert state.design == {"a/b": 1}
    state = apply_changes(state, [{"op": "replace", "path": "/design/a~1b", "value": 2}])
    assert state.design == {"a/b": 2}
    assert apply_changes(state, [{"op": "remove", "path": "/design/a~1b"}]).design == {}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ([], "at least one operation"),
        ([{"op": "move", "path": "/goal"}], "expected add, replace or remove"),
        ([{"op": "replace", "path": "/version", "value": 9}], "top-level key"),
        ([{"op": "add", "path": "/requirements/-", "value": {"text": "x"}}], "needs an id"),
        ([{"op": "remove", "path": "/requirements/R2"}], "one of R1"),
        ([{"op": "add", "path": "/requirements/R2", "value": R1}], "'-' to append"),
        ([{"op": "add", "path": "/requirements/-", "value": R1}], "expected each id once"),
        ([{"op": "add", "path": "/assumptions/-", "value": {"id": "A2"}}], "text"),
        ([{"op": "replace", "path": "/design/missing", "value": 1}], "does not exist"),
        ([{"op": "add", "path": "/goal/deep", "value": 1}], "into an object"),
    ],
)
def test_an_invalid_patch_says_how_to_fix_it(changes, message):
    """A patch that does not fit raises ``StateError``, and the model reads the reason."""
    with pytest.raises(StateError, match=message):
        apply_changes(with_items(), changes)


def test_a_patch_applies_whole_or_not_at_all():
    """A failing last operation leaves nothing of the first."""
    state = with_items()
    with pytest.raises(StateError):
        apply_changes(
            state,
            [
                {"op": "replace", "path": "/goal", "value": "x"},
                {"op": "remove", "path": "/questions/Q9"},
            ],
        )
    assert state.goal == ""


def test_an_untouched_state_renders_nothing():
    """An empty state adds no message to a call."""
    assert render(ProblemState()) == ""


def test_render_gives_one_line_per_item():
    """Every kind of item is one compact line."""
    state = apply_changes(
        with_items(),
        [
            {"op": "replace", "path": "/goal", "value": "Size it"},
            {"op": "add", "path": "/design/plant", "value": "doublet"},
            {"op": "add", "path": "/results/-", "value": {"id": "X1", "summary": "ok"}},
            {
                "op": "add",
                "path": "/results/-",
                "value": {"id": "X2", "summary": "b", "reference": "r"},
            },
            {"op": "add", "path": "/verification/mass", "value": "pass"},
            {"op": "add", "path": "/questions/-", "value": {"id": "Q1", "text": "Depth?"}},
        ],
    )
    assert render(state).splitlines() == [
        "Problem state, version 2",
        "Goal: Size it",
        "Requirement R1 [open]: Cover the load (case requirement heat_delivered)",
        "Assumption A1 [unconfirmed, user]: Inlet temperature = 80",
        'Design: {"plant": "doublet"}',
        "Result X1: ok",
        "Result X2: b (r)",
        'Verification: {"mass": "pass"}',
        "Question Q1: Depth?",
    ]


def test_render_keeps_a_requirement_without_a_case_requirement_short():
    """Optional fields leave no trace."""
    state = apply_changes(
        ProblemState(),
        [
            {"op": "add", "path": "/requirements/-", "value": {"id": "R1", "text": "Be safe"}},
            {"op": "add", "path": "/assumptions/-", "value": {"id": "A1", "text": "Dry"}},
        ],
    )
    assert render(state).splitlines()[1:] == [
        "Requirement R1 [open]: Be safe",
        "Assumption A1 [unconfirmed, agent]: Dry",
    ]


@example_names
def test_a_state_with_a_case_round_trips_as_json(name):
    """The case is plain data: a state dumped to JSON and validated again is equal."""
    case = example_case(name)[0]
    state = apply_changes(ProblemState(), [{"op": "replace", "path": "/case", "value": case}])
    assert state.case == case
    assert ProblemState.model_validate(json.loads(state.model_dump_json())) == state


def test_a_patch_can_change_one_value_of_the_case():
    """``case`` is a key of the document, so a path may go below it."""
    case = example_case("shallow_district")[0]
    state = apply_changes(ProblemState(), [{"op": "replace", "path": "/case", "value": case}])
    state = apply_changes(
        state, [{"op": "replace", "path": "/case/time/start", "value": "2026-01-13"}]
    )
    assert state.case["time"]["start"] == "2026-01-13"
    assert state.case["demand"] == case["demand"]


@example_names
def test_render_shows_the_case_briefly(name):
    """The line names the time and the sections, never the demand values."""
    case = example_case(name)[0]
    state = apply_changes(ProblemState(), [{"op": "replace", "path": "/case", "value": case}])
    line = render(state).splitlines()[1]
    assert line.startswith(f"Case: time {case['time']['start']} to {case['time']['end']}")
    assert "demand heating in data/demand.csv, cooling in data/demand.csv" in line
    assert len(line) < 300


def test_a_requirement_is_text_with_a_link_to_a_case_requirement_never_a_target():
    """A number is a requirement of the case; the requirement keeps the words and its name."""
    state = with_items()
    assert state.requirements[0].case_requirement == "heat_delivered"
    assert "(case requirement heat_delivered)" in render(state)
    with pytest.raises(StateError, match="metric"):
        apply_changes(
            ProblemState(),
            [{"op": "add", "path": "/requirements/-", "value": {**R1, "metric": "coverage"}}],
        )


def test_an_assumption_keeps_its_reason_and_its_source_details():
    """A value the user confirmed carries why it was chosen and where it came from."""
    from geomind.context.state import Assumption, ProblemState, render

    cited = {"title": "A cost survey", "publisher": "An agency", "year": 2020, "page": "12"}
    item = Assumption(
        id="A1", text="gas price", value=0.04, reason="the files give none", citation=cited
    )
    text = render(ProblemState(assumptions=(item,), version=1))
    assert "because the files give none" in text and "A cost survey" in text
    assert Assumption.model_validate(item.model_dump()).citation == cited


def test_removing_a_key_that_is_gone_changes_nothing():
    """QA-317: a loop removed ``/design/reference`` a driver had removed, and the run failed."""
    state = apply_changes(ProblemState(), [{"op": "add", "path": "/design/rejected", "value": []}])
    cleared = apply_changes(state, [{"op": "remove", "path": "/design/reference"}])
    assert cleared.design == {"rejected": []}


def test_a_finding_of_another_minor_version_is_marked_in_the_render():
    """QA-346: a finding of another minor geomind or gemini is marked; a patch release is not."""
    from geomind.context.state import apply_changes, render, tools_version

    finding = {"id": "F1", "agent": "economist", "task": "t", "summary": "no P10", "reference": "f"}
    state = apply_changes(ProblemState(), [{"op": "add", "path": "/findings/-", "value": finding}])
    assert state.findings[0].made_under == tools_version()
    assert "made under" not in render(state)

    def made(versions):
        item = state.findings[0].model_copy(update={"made_under": versions})
        return render(state.model_copy(update={"findings": (item,)}))

    geomind, gemini = (part.split()[1] for part in tools_version().split(" / "))
    patched = ".".join([*geomind.split(".")[:2], "999"])
    assert "made under" not in made(f"geomind {patched} / gemini {gemini}")
    note = "made under geomind 0.1.0 / gemini 0.6.0; check it against the current tools"
    assert note in made("geomind 0.1.0 / gemini 0.6.0")
    assert "made under an earlier geomind" in made(None)

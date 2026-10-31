"""The brief as data: optional fields, the hackathon preset, patches, render and storage."""

import asyncio

import pytest
from pydantic import ValidationError

import geomind as gd
from geomind.context import (
    PRESETS,
    Brief,
    ProblemState,
    apply_changes,
    preset,
    render,
    with_changes,
)
from geomind.errors import StateError
from geomind.providers import FakeLLM
from tests.fixtures.runs import Worker, context, says

HACKATHON = preset("hackathon_2027")


def test_every_field_is_optional():
    """An empty brief gives nothing: ``None`` is "not given"."""
    assert Brief().model_dump(exclude_none=True) == {}


def test_the_hackathon_preset_holds_the_brief_s_numbers():
    """The registry is the only place they live."""
    assert set(PRESETS) == {"hackathon_2027"}
    assert (HACKATHON.doublets.min, HACKATHON.doublets.max) == (1, 3)
    assert (HACKATHON.doublet_flow.min, HACKATHON.doublet_flow.max) == ("50 m3/h", "300 m3/h")
    assert (HACKATHON.heating.supply, HACKATHON.cooling.supply) == ("100 degC", "20 degC")
    assert HACKATHON.heating.return_temperature is None
    assert HACKATHON.reservoir.gas_composition == {"CH4": 0.8, "CO2": 0.2}


def test_an_unknown_preset_names_the_known_ones():
    """A wrong name raises with the list."""
    with pytest.raises(StateError, match="hackathon_2027"):
        preset("hackathon")


def test_changes_merge_into_records_and_none_removes():
    """A change replaces one field of a nested record and keeps the others."""
    changed = with_changes(HACKATHON, {"doublets": {"max": 1}, "operating_days": None})
    assert (changed.doublets.min, changed.doublets.max) == (1, 1)
    assert changed.operating_days is None
    with pytest.raises(ValidationError):
        with_changes(HACKATHON, {"doublet": 2})


def test_a_patch_sets_the_brief_and_render_shows_it():
    """``/brief`` is a key of the state; ``render`` gives it to every agent."""
    value = HACKATHON.model_dump(mode="json")
    state = apply_changes(ProblemState(), [{"op": "replace", "path": "/brief", "value": value}])
    state = apply_changes(state, [{"op": "replace", "path": "/brief/doublets/max", "value": 2}])
    assert state.brief.doublets.max == 2
    assert '"source": "hackathon_2027"' in render(state)


def test_a_state_with_a_brief_round_trips_through_save_state(tmp_path):
    """The engine saves the state at the end of a run; the brief comes back whole."""
    store = gd.stores.FileRunStore(tmp_path)
    problem = ProblemState(version=1, brief=with_changes(HACKATHON, {"doublets": {"max": 2}}))
    engine = gd.Engine(llm=FakeLLM([says("ok")]), store=store)
    asyncio.run(engine.run(Worker(), context(chat="c1", problem=problem)))
    loaded = ProblemState.model_validate(gd.stores.FileRunStore(tmp_path).load_state("c1"))
    assert loaded.brief == problem.brief

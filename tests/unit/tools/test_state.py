"""The tool that writes the problem state."""

from geomind.tools import update_state


def test_update_state_is_a_write_that_a_crash_cannot_repeat():
    """A rerun would apply the patch twice; a replay reruns it, over its own log."""
    assert update_state.effect == "write"
    assert update_state.idempotent is False
    assert update_state.replays is True


def test_the_schema_hides_the_context():
    """The model sees only the changes."""
    assert list(update_state.input_schema["properties"]) == ["changes"]

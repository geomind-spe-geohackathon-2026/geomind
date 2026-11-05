"""run_python's inputs: a stored list as data, and the literals the code may hold."""

from geomind.engine import Context
from geomind.tools import dispatch
from geomind.tools.python import _inputs, _results, literal_problems
from geomind.tools.stored import reference_of
from tests.fixtures.sessions import StubSession
from tests.unit.tools.test_stored import call, plants


async def test_a_stored_list_is_one_data_input_with_its_source():
    """QA-205: a study's history reaches the code whole; the calculation does not copy it."""
    session = StubSession()
    await dispatch(plants, call(), Context(session=session))
    key = reference_of("c1")
    resolved = _inputs(Context(session=session), {"rows": {"stored": key, "path": "plants"}})
    assert len(resolved[0]["value"]) == 30 and resolved[0]["unit"] is None
    assert resolved[0]["source"] == {"kind": "stored", "reference": key, "path": "plants"}
    found = _results({"n": {"value": 30, "unit": "-"}}, "P1", resolved, "code")
    assert "value" not in found[0]["operands"][0]


def test_whole_small_floats_are_no_data_literals():
    """QA-205: 0.0 is a start value, not data; 300 and 1e-06 still are."""
    found = literal_problems("a = 0.0\nb = 1.0\nc = 300\nd = 1e-06\n")
    assert found == ["line 3: 300", "line 4: 1e-06"]

"""QA-296: a call its tool would refuse is refused before its approval card, never after."""

from types import SimpleNamespace

from geomind import runtime
from geomind.engine import Context
from geomind.engine.step import _prechecked
from geomind.tools.python import literal_problems, run_python
from geomind.tools.web import read_web_page
from geomind.types import ToolCall
from tests.fixtures.sessions import StubSession


def session_with_sandbox():
    """Return a session whose engine has a sandbox, and whose context is the engine's."""
    session = StubSession()
    session.engine = SimpleNamespace(sandbox=object())
    return SimpleNamespace(context=lambda: Context(session=session))


def test_slice_bounds_widths_and_round_digits_are_no_data_literals():
    """``repr(h)[:300]`` and ``ljust(20)`` lay out text; a value of the problem is still data."""
    code = "a = repr(h)[:300]\nb = name.ljust(20)\nc = round(x, 3)\nd = rows[-400:]\ne = 300\n"
    assert literal_problems(code) == ["line 5: 300"]


async def test_run_python_with_a_data_literal_is_refused_before_its_card():
    """Six run_python cards were approved and then refused for their literals."""
    asked = ToolCall(id="c1", name="run_python", input={"purpose": "sum", "code": "x = 300\n"})
    refused = await _prechecked(session_with_sandbox(), run_python, asked)
    assert refused is not None and refused.is_error
    assert "data literals" in refused.output["error"]["message"]


async def test_read_web_page_of_a_host_that_is_not_public_is_refused_before_its_card():
    """Three cards for https://example.invalid were approved and then refused."""
    asked = ToolCall(id="c1", name="read_web_page", input={"url": "https://example.invalid"})
    with runtime.settings(search_url="http://search.test"):
        refused = await _prechecked(session_with_sandbox(), read_web_page, asked)
    assert refused is not None and refused.output["error"]["code"] == "not_allowed"

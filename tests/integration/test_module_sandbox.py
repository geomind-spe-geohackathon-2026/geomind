"""test_module on the real image ``gemini-sandbox:<version>``; it runs only with ``-m docker``."""

import shutil
import subprocess

import pytest

from geomind.engine import Context
from geomind.sandbox import DockerSandbox
from geomind.tools import dispatch
from geomind.tools.gemini import test_module
from geomind.types import ToolCall
from tests.fixtures.modules import BROKEN, EXAMPLE, GOOD
from tests.fixtures.sessions import StubSession

pytestmark = pytest.mark.docker


def has_image():
    """Tell whether Docker answers and holds the image of this gemini version."""
    import gemini as gm

    if shutil.which("docker") is None:
        return False
    image = f"gemini-sandbox:{gm.__version__}"
    return (
        subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0
    )


class Engine:
    """Holds the Docker provider."""

    sandbox = DockerSandbox()


async def tested(code, **tool_input):
    """Store a module, test it in a container and return the output."""
    session = StubSession()
    session.engine = Engine()
    session.artifacts["module/m.py"] = code
    call = ToolCall(id="c1", name="test_module", input={"name": "m", **tool_input})
    return (await dispatch(test_module, call, Context(session=session))).output


@pytest.mark.skipif(not has_image(), reason="needs Docker and `make sandbox-image` in gemini")
async def test_a_correct_module_passes_in_the_container():
    """The check of gemini passes it."""
    output = await tested(GOOD, example=EXAMPLE)
    assert output["passed"] is True and output["modules"] == ["ResistanceHeater"]


@pytest.mark.skipif(not has_image(), reason="needs Docker and `make sandbox-image` in gemini")
async def test_a_broken_module_fails_with_gemini_s_problems():
    """The problems name the failed checks."""
    output = await tested(BROKEN)
    paths = {item["path"] for item in output["problems"]}
    assert output["passed"] is False and {"Wrong.units", "Wrong.forward_signature"} <= paths

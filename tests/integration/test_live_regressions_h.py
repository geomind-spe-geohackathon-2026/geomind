"""Bugs of the case team's Track A rounds, each from a recorded call (#65, #66)."""

import json
from pathlib import Path

from geomind.tools.gemini.case import set_case
from tests.fixtures.calls import call
from tests.integration.test_live_regressions_c import session_with_files

CALLS = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "live" / "track_a_set_case.json").read_text()
)


async def test_a_gradient_in_degc_per_km_gets_k_per_km():
    """#66: ``degC/km`` was answered with ``{'unit': 'degC'}`` and the units of temperature.

    gemini 0.6.3 takes ``degC/km`` (request 31), so a unit it does not take shows the error.
    """
    arguments = json.loads(json.dumps(CALLS["together"]).replace("degC/km", "degF/km"))
    output = (await call(set_case, arguments, session_with_files(), "p")).output
    suggestions = output["error"]["suggestions"]
    assert any(item.startswith("site.ground.gradient: accepted units: ") for item in suggestions)
    assert any("degC/km" in item for item in suggestions)
    assert not any("'unit': 'degC'}" in item for item in suggestions)


async def test_the_recorded_degc_per_km_is_gemini_s():
    """#115: the recorded call's ``degC/km`` gives no gradient error (gemini 0.6.3, request 31)."""
    output = (await call(set_case, CALLS["together"], session_with_files(), "p")).output
    assert "gradient" not in output["error"]["message"]


async def test_files_the_changes_name_load_without_files():
    """#65: the case lead sent the files and the changes in separate calls; now one is enough."""
    output = (await call(set_case, CALLS["together"], session_with_files(), "p")).output
    message = output["error"]["message"]
    assert "not found" not in message and "first column" not in message


async def test_files_alone_on_no_case_name_what_they_need():
    """#65: files with no changes on an empty case got the header error, which says nothing."""
    output = (await call(set_case, CALLS["files_alone"], session_with_files(), "p")).output
    error = output["error"]
    assert error["code"] == "case_incomplete"
    assert "loads the project files the changes name" in error["message"]

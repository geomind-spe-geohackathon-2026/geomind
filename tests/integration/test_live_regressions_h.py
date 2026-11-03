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
    """#66: ``degC/km`` was answered with ``{'unit': 'degC'}`` and the units of temperature."""
    output = (await call(set_case, CALLS["together"], session_with_files(), "p")).output
    suggestions = output["error"]["suggestions"]
    assert "accepted units: K/km, K/m" in suggestions
    assert not any("'unit': 'degC'}" in item for item in suggestions)


async def test_the_files_retry_says_to_send_everything_again():
    """#65: told ``changes=<the same changes>``, the case lead sent the files alone, 3 times."""
    output = (await call(set_case, CALLS["together"], session_with_files(), "p")).output
    retry = next(item for item in output["error"]["suggestions"] if item.startswith("set_case("))
    assert "requirements and economics" in retry and "stored nothing" in retry


async def test_files_alone_on_no_case_name_what_they_need():
    """#65: files with no changes on an empty case got the header error, which says nothing."""
    output = (await call(set_case, CALLS["files_alone"], session_with_files(), "p")).output
    error = output["error"]
    assert error["code"] == "case_incomplete" and "in the same call" in error["message"]

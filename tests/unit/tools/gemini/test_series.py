"""``repair_series``: a few rows of a series file changed, never the whole series retyped."""

import io

import pandas as pd

from geomind.tools.gemini.series import repair_series
from tests.fixtures.calls import call
from tests.fixtures.cases import case_context
from tests.fixtures.sessions import StubSession


async def demand_case():
    """Return the session and state of the hackathon case, and its heating file and column."""
    session = StubSession()
    context = await case_context("hackathon_2026", session)
    power = context.problem.case["demand"]["heating"]["power"]
    return session, context.problem, power["file"], power["column"]


async def test_two_days_of_the_case_s_demand_are_changed_and_the_rest_kept():
    """QA-318: two rows by date and by index; the case names the new file."""
    session, problem, file, column = await demand_case()
    original = pd.read_csv(io.BytesIO(session.artifacts[f"case/{file}"]))
    first_time = str(original.iloc[0, 0])[:10]
    rows = {first_time: 1.5, "2": 2.5}
    arguments = {"file": file, "rows": rows, "name": "fixed", "column": column}
    result = await call(repair_series, arguments, session, problem=problem)
    assert not result.is_error, result.output
    assert [item["new"] for item in result.output["changed"]] == [1.5, 2.5]
    case = session.changes[-1][0]["value"]
    assert case["demand"]["heating"]["power"]["file"] == "data/fixed.csv"
    fixed = pd.read_csv(io.BytesIO(session.artifacts["case/data/fixed.csv"]))
    assert list(fixed[column][[0, 2]]) == [1.5, 2.5]
    assert fixed[column][3:].tolist() == original[column][3:].astype(float).tolist()


async def test_a_time_the_file_lacks_is_refused_with_times_near_it():
    """An unknown row names the times close to it; nothing is stored."""
    session, problem, file, column = await demand_case()
    arguments = {"file": file, "rows": {"1999-01-01": 1.0}, "name": "fixed", "column": column}
    result = await call(repair_series, arguments, session, problem=problem)
    assert result.is_error and result.output["error"]["path"] == "rows.1999-01-01"
    assert "case/data/fixed.csv" not in session.artifacts

"""``repair_series``: a few rows of a series file changed, never the whole series retyped."""

import io

import pandas as pd

from geomind.tools.gemini.series import repair_series
from tests.fixtures.calls import call
from tests.fixtures.cases import case_context
from tests.fixtures.sessions import StubSession


async def flawed_case():
    """Return the session, state, file and column of the hackathon case, its file made flawed.

    The file gets the header ``date`` (QA-318's file), loses its third day (a gap) and its fifth
    day turns negative.
    """
    session = StubSession()
    context = await case_context("hackathon_2026", session)
    power = context.problem.case["demand"]["heating"]["power"]
    key = f"case/{power['file']}"
    table = pd.read_csv(io.BytesIO(session.artifacts[key]))
    table.columns = ["date", *table.columns[1:]]
    gap = str(table.at[2, "date"])
    table.loc[4, power["column"]] = -table.at[4, power["column"]]
    table = table.drop(index=2).reset_index(drop=True)
    session.artifacts[key] = table.to_csv(index=False).encode()
    return session, context.problem, power, gap


async def test_a_gap_and_a_negative_day_are_repaired_into_a_case_gemini_accepts():
    """QA-318: a missing day is added, a negative one set, the neighbours shown, the case stored."""
    session, problem, power, gap = await flawed_case()
    negative = str(pd.read_csv(io.BytesIO(session.artifacts[f"case/{power['file']}"])).iat[3, 0])
    table = pd.read_csv(io.BytesIO(session.artifacts[f"case/{power['file']}"]))
    both = {name: 20.0 for name in table.columns[1:]}
    rows = {gap: both, negative: 21.0}
    arguments = {"file": power["file"], "rows": rows, "name": "fixed", "column": power["column"]}
    result = await call(repair_series, arguments, session, problem=problem)
    assert not result.is_error, result.output
    added, changed = result.output["changed"][0], result.output["changed"][-1]
    assert added["added"] and added["old"] is None and len(added["neighbours"]) == 2
    assert changed["old"] < 0 and changed["new"] == 21.0
    assert session.changes[-1][0]["value"]["demand"]["heating"]["power"]["file"] == "data/fixed.csv"
    fixed = pd.read_csv(io.BytesIO(session.artifacts["case/data/fixed.csv"]))
    assert fixed.columns[0] == "time" and str(fixed.iat[2, 0]) == gap
    again = {"file": "data/fixed.csv", "rows": {"0": 22.0}, "name": "fixed2"}
    arguments = {**again, "column": power["column"]}
    assert not (await call(repair_series, arguments, session, problem=problem)).is_error


async def test_a_row_that_is_no_time_is_refused_with_times_near_it():
    """A key that is neither a time nor an index names the file's times; nothing is stored."""
    session, problem, power, _ = await flawed_case()
    arguments = {"file": power["file"], "rows": {"day-x": 1.0}, "name": "fixed",
                 "column": power["column"]}
    result = await call(repair_series, arguments, session, problem=problem)
    assert result.is_error and result.output["error"]["path"] == "rows.day-x"
    assert "case/data/fixed.csv" not in session.artifacts

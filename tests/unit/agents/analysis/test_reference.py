"""The analysis team's gemini reference: made from gemini, so names never drift (Track C)."""

import re

from geomind.agents import AnalysisLead, Economist
from geomind.agents.analysis.reference import metrics

OBJECTIVES = {"annualised_cost", "lcts", "lcoh", "lcoc", "co2"}
"""gemini 0.6.1's metrics a study may minimise; a change of gemini's fails here first."""


def metric_names():
    """Return gemini's metric names."""
    return {item["name"] for item in metrics()}


def test_gemini_s_objectives_are_the_ones_the_prompts_were_written_for():
    """The economist ranks on these; gemini renaming one must change the prompts too."""
    assert {item["name"] for item in metrics() if item["objective"]} == OBJECTIVES


def test_every_metric_reaches_both_prompts_with_its_unit():
    """Each metric line names gemini's unit, in the rendered prompt of both agents."""
    for agent in (AnalysisLead(), Economist()):
        text = agent.prompt.render()
        for item in metrics():
            assert f"- `{item['name']}`: {item['title']}, in {item['unit']}" in text


def test_the_metrics_the_prompts_cite_are_gemini_s():
    """``lcts``, ``co2`` and the rest, in backticks in the hand-written text, exist in gemini."""
    for agent in (AnalysisLead(), Economist()):
        cited = set(
            re.findall(r"`(lc[a-z]+|co2|capex|opex|annualised_cost)`", agent.prompt.content)
        )
        assert cited <= metric_names()


def test_the_economics_keys_come_with_their_meanings():
    """The economist reads the economics keys of gemini's schema, with geomind's meanings."""
    text = Economist().prompt.render()
    assert "discount_rate: {value} (number) — real discount rate per year, 0-1" in text
    assert "price_year" in text and "## Study keys" in text


def test_the_economist_never_works_out_a_difference():
    """A comparison is gemini's ranks and values, never a difference or a share it computed."""
    text = " ".join(Economist().prompt.content.split())
    assert "never a difference or a percentage you work out" in text
    assert "never add, subtract, share or average its parts" in text


def test_a_cost_task_is_costs_only():
    """#85: told to cost a design, the economist sampled 200 draws with a seed it chose."""
    text = " ".join(Economist().prompt.content.split())
    assert "only when the task asks for an uncertainty" in text


def test_compute_kpis_is_called_without_names():
    """#88: the analysis lead asked compute_kpis for annualised_cost, a cost metric it lacks."""
    text = AnalysisLead().prompt.render()
    assert "`compute_kpis` has names of its own" in text and "call it without `names`" in text


def test_a_study_s_metrics_are_gemini_s():
    """A study refuses ``capex`` (nemotron sampled it): the prompt names what a study reads.

    gemini keeps the list in a private module (request C-1): this pin fails when it changes.
    """
    from gemini.study._utils.trial import ECONOMICS, KPI_NAMES

    from geomind.agents.analysis.reference import STUDY_KPIS

    assert tuple(KPI_NAMES) == STUDY_KPIS and set(ECONOMICS) == OBJECTIVES
    assert "never `capex` or `opex`" in Economist().prompt.render()

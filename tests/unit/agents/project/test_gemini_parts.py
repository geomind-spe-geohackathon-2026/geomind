"""The project team's prompts follow gemini and the Route: a name that changes fails here."""

import re
import typing

from geomind.agents.project.coordinator import ROUTE_OPTIONS, Coordinator, Route
from geomind.agents.project.explainer import Explainer
from geomind.agents.project.reviewer import Reviewer
from geomind.tools.gemini.verdict_text import metric_names, reason_kinds


def test_every_route_option_is_explained_and_none_is_extra():
    """The coordinator's prompt explains each value of ``kind``, ``loop`` and ``agent``."""
    for field, options in ROUTE_OPTIONS.items():
        allowed = set(typing.get_args(Route.model_fields[field].annotation))
        assert set(options) == allowed, field
    text = Coordinator().prompt.render()
    assert "## Route options" in text and "- `compare`:" in text


def test_the_reviewer_reads_gemini_s_reason_kinds_and_metrics():
    """The kinds come from ``gm.evaluate.verdict``'s docstring, the metrics from gemini."""
    assert set(reason_kinds()) == {"requirement", "failed_step", "numerical", "bound"}
    text = Reviewer().prompt.render()
    assert "- `failed_step`:" in text and "- `lcoh`:" in text and "`failures` groups" in text


def test_every_metric_the_project_prompts_name_is_gemini_s():
    """``heat_delivered``, ``lcoh``, ``lcts`` ...: a metric gemini renames fails here."""
    cited = {"heat_delivered", "cold_delivered", "lcoh", "lcoc", "lcts", "co2", "capex", "opex"}
    assert cited <= metric_names()
    for agent in (Reviewer(), Explainer()):
        named = set(re.findall(r"`(\w+)` \d", agent.prompt.content))
        assert named <= metric_names()


def test_the_costs_are_said_to_come_from_estimate_costs():
    """#105: the explainer asked ``compute_kpis`` for ``annualised_cost``, which it has not."""
    from geomind.tools.gemini.assessment import COSTS
    from geomind.tools.gemini.verdict_text import metrics_reference

    text = metrics_reference()
    assert "without `names`" in text and "come from `estimate_costs`" in text
    assert all(f"`{name}`" in text for name in COSTS)


def test_the_reviewer_and_the_explainer_keep_what_they_read():
    """#106: 37 ``read_result`` and 17 ``read_stored`` calls on results that shrank in one step."""
    for agent, names in (
        (Reviewer(), ("check_results", "compute_kpis", "read_case", "read_result")),
        (Explainer(), ("compute_kpis", "estimate_costs", "read_plant", "read_result")),
    ):
        assert all(agent.tools()[name].keeps_result for name in names)


def test_the_reviewer_reads_the_state_from_the_conversation():
    """#108: the reviewer tried ``read_stored("state")``; the state is a message, not a tool."""
    text = " ".join(Reviewer().prompt.content.split())
    assert "the `Problem state` message at the end of the conversation" in text


def test_the_lead_skips_a_set_case_and_stops_after_two_same_answers():
    """#109: the lead briefed the case lead on a set case, and a team 14 times on one answer."""
    from geomind.agents.project.lead import ProjectLead

    text = " ".join(ProjectLead().prompt.content.split())
    assert "needs no case step" in text and "gets no third brief" in text


def test_the_explainer_keeps_what_it_read_for_the_whole_run():
    """#106: the explainer read its whole input set three times, each time it shrank."""
    tools = Explainer().tools()
    assert all(tools[name].keeps_result == "run" for name in ("compute_kpis", "read_result"))


def test_the_explainer_quotes_plant_values_in_their_own_units():
    """#110: ``1500000.0 W/K`` became ``1.5 MW/K``; ``read_plant`` gives display units (30)."""
    text = " ".join(Explainer().prompt.content.split())
    assert "values in gemini's display units too" in text and "never in another unit" in text
    assert "`compute_kpis`'s `capacities`" in text


def test_the_lead_offers_no_example_value_in_a_question():
    """#111: the lead asked for the air humidity "in %, e.g. 70", a typical value of its own."""
    from geomind.agents.project.lead import ProjectLead

    text = " ".join(ProjectLead().prompt.content.split())
    assert "never offer a value or an example number of your own" in text

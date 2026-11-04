"""The case_lead: sets the case from the project's files and the user's answers."""

from geomind import runtime
from geomind.agents import CaseLead, DesignLead
from tests.unit.agents.structure import check_complete

TOOLS = [
    "geoscientist",
    "list_files",
    "read_rag",
    "search_rag",
    "read_case",
    "describe_case",
    "set_case",
    "ask_economics",
    "save_profile",
    "list_profiles",
    "read_profile",
    "read_stored",
    "search_memory",
    "read_memory",
    "update_state",
    "support_lead",
    "ask_user",
    "finish",
]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(CaseLead, "case/lead", TOOLS)


def test_only_the_formulator_sets_the_case():
    """The design lead reads the case and never sets it or reads the files."""
    design_lead = set(DesignLead().tools())
    assert "set_case" in CaseLead().tools() and "read_case" in design_lead
    assert not design_lead & {"set_case", "save_profile", "list_files", "read_rag"}


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_CASELEAD_MODEL`` has no fallback: without it the role has no model."""
    monkeypatch.delenv("GEOMIND_CASELEAD_MODEL", raising=False)
    assert runtime.role_models()["caselead"] is None
    assert "GEOMIND_CASELEAD_MODEL" in runtime.missing_model_settings()


def test_values_no_file_gives_are_confirmed_in_one_question():
    """Every value not from the files is listed with its source or reason, and the user decides."""
    text = " ".join(CaseLead().prompt.render().split())
    assert "ONE confirmation question" in text
    assert "`approve all`, `change some` and `stop`" in text
    assert "confirmed: true" in text and "`price_year`" in text


def test_the_case_is_set_in_parts():
    """The test run sent the whole case five times; the prompt and set_case say to send parts."""
    from geomind.tools.gemini.case import set_case

    text = " ".join(CaseLead().prompt.render().split())
    assert "Once a case is stored, send only the keys that change" in text
    assert "send only" in set_case.description or "send only" in set_case.function.__doc__


def test_it_computes_nothing_and_invents_no_number():
    """#43 and #44: a derived value stays unset for gemini; a value with no source is asked."""
    text = CaseLead().prompt.content
    assert "Compute nothing" in text and "stays unset" in text
    assert "with no number of your own" in text


def test_it_writes_no_number_it_worked_out():
    """#64: a dew point worked out inside a question; the span is copied from the file."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "every number you write, in a question" in text and "a dew point" in text
    assert "from the `span` of the data file's `table`" in text


def test_a_missing_value_is_searched_before_it_is_asked_for():
    """Sahand: files, then the knowledge base, then MCP, and only then the user."""
    text = " ".join(CaseLead().prompt.content.split())
    order = ["the project's files", "the knowledge base:", "`read_mcp`", "only when none"]
    assert [text.index(item) for item in order] == sorted(text.index(item) for item in order)
    assert "ALWAYS, also when the files seem complete" in text
    assert '`read_rag("knowledge/cost-sources.csv", columns=[...])`' in text
    assert "knowledge/cost-sources.csv" in text and "`placeholder`" in text


def test_time_end_is_exclusive_and_the_data_decides_the_span():
    """#58: the case lead read a year ending on 31 Dec as 364 steps and proposed to drop a day.

    gemini 0.6.3's schema says ``time.end`` is excluded (request 12): the prompt only points to it.
    """
    from geomind.tools.gemini.fields import case_fields

    text = " ".join(CaseLead().prompt.content.split())
    assert "`time.end` (excluded, as its description says)" in text and "never the data" in text
    assert "365 steps" in case_fields()["time.end"]


def test_it_knows_the_case_format_s_traps():
    """Durations are no counts; supply and return sides; the brine's gas is no grid gas."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "never a `count`" in text and "cooling (chilled water) return is warmer" in text
    assert "Never put one in the other" in text and "Checklist before you hand over" in text


def test_its_key_tree_says_what_each_field_means():
    """The case keys carry their source, the derived ones, and every requirement option.

    The meanings come from ``describe_case``, on demand (Track A).
    """
    text = CaseLead().prompt.render()
    assert "site.reservoir.temperature: {value, unit} [derived]" in text
    assert "`describe_case(path)`" in text
    assert "duration: the total time of the steps" in text and "count: how many units" in text


def test_a_change_reports_the_value_before_as_the_case_showed_it():
    """#62: the case lead said a cap was 200 while the case held 300; it reads before and after."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "before and after it with `read_case`" in text and "never from memory" in text


def test_it_reads_once_asks_once_and_copies_digits():
    """Track A: 12 read_stored calls, three questions for the same values, rounded prices."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "never read it again" in text and "Never ask for it again" in text
    assert "digit for digit" in text and "as few `set_case` calls as you can" in text
    assert "read once with `columns`" in text


def test_it_chooses_among_the_catalogue_s_rows_by_their_status():
    """Several catalogue rows per key: sourced, then verified, then one question for the rest.

    A row whose unit the key does not accept never goes in (Sahand's catalogue of 133 rows).
    """
    text = " ".join(CaseLead().prompt.content.split())
    order = ["beats a `placeholder`", "`verified` row beats a `secondary`", "the latest `year`"]
    assert [text.index(item) for item in order] == sorted(text.index(item) for item in order)
    assert "`EUR/W heat` is `EUR/W`" in text and "never goes in: list it as not usable" in text


def test_a_refused_full_call_is_sent_again_whole():
    """#69: files alone after a refused full call, the geoscientist after ``already_asked``."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "send the SAME full call again" in text and "never a files-only call" in text
    assert "after `already_asked`, never call it again" in text
    assert "File names are case-sensitive" in text


def test_units_are_written_as_the_source_gives_them():
    """#115: set_case maps °C/km and mol%; the lead lists what it converted in the one question."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "`30 °C/km`, `80 mol%`" in text and "`converted`" in text


def test_a_flaw_of_a_loaded_case_is_always_a_question():
    """#119: nemotron named the flaws of a loaded case in its answer and asked nothing."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "Each flaw is ALWAYS a question with `ask_user` before you finish" in text
    assert 'Don\'t: finish with "Flaws found (need your input)" in the answer' in text
    assert "every flaw found was asked about with `ask_user`" in text


def test_economics_are_a_required_step_after_the_case():
    """#121: nemotron set the project case and no economics; it said it would offer rows "next".

    The workflow's numbered step 5 reads the catalogue once, asks one question with each value's
    row and sets the economics; the checklist and the stop rule name them too.
    """
    text = " ".join(CaseLead().prompt.content.split())
    steps = ["1. `list_files`", "3. `set_case`", "4. The ONE confirmation"]
    steps += ["5. Economics, REQUIRED"]
    assert [text.index(step) for step in steps] == sorted(text.index(step) for step in steps)
    step = text[text.index("5. Economics") : text.index("6. `read_case`")]
    assert "never twice" in step and "ONE `ask_economics` call" in step
    assert "`currency`, `price_year` and `discount_rate` too" in step and "row `id`" in step
    assert "the others in `others`" in step
    assert "the tool sets every value with its row" in step
    assert "the economics are set (step 5)" in text and "and its economics set" in text


TASK = (
    "Set up the case from the organiser's brief and the two demand files. The user wants a "
    "geothermal heating and cooling plant designed and verified. Read the organiser's brief and "
    "the demand files, and build the case (time, site, demand, utilities, requirements, "
    "initial_state). Report any missing values as case change needed lines with paths and reasons."
)
"""The project lead's brief to the case lead in the end-to-end run, as recorded (#124)."""
ANSWER = (
    "The case is set (version 1) with all values from the brief and demand files. Now I need to "
    "ask you for all values that no file or source provides, in one question."
)
"""The delegated case lead's text answer that ended its run with no economics, as recorded."""


async def test_a_delegated_case_lead_without_economics_is_sent_back_once():
    """#124: a run that set the case with no economics and asked nothing is refused once.

    The refusal names step 5, also on a text answer; an answer after the refusal ends the run.
    """
    from geomind.context import ProblemState
    from geomind.engine import Context
    from geomind.types import Message
    from tests.fixtures.runs import call, engine_for, says, uses

    case = {"name": "GEMINI Hackathon 2027", "time": {"start": "2027-01-01"}}
    completions = [
        uses(call("set_case", "c1", changes={"name": "GEMINI Hackathon 2027"})),
        says(ANSWER),
        says("Economics open: the user was not asked."),
    ]
    engine = engine_for(completions)
    start = Context(messages=[Message(role="user", content=TASK)], problem=ProblemState(case=case))
    result = await engine.run(CaseLead(), start)
    assert result.status == "done" and result.answer.startswith("Economics open")
    events = engine.store.load_events(result.run_id)
    [refusal] = [item for item in events if getattr(item, "feedback", None) == "finish"]
    assert refusal.output.startswith("economics not done")
    assert "ask_economics" in refusal.output and "on approve all it sets them" in refusal.output


def test_the_economics_check_passes_with_economics_an_economics_question_or_no_set_case():
    """No refusal for a case with economics, a run that asked about them, or one that set none."""
    from geomind.agents.case.lead import economics_missing
    from geomind.context import ProblemState
    from geomind.engine import Context
    from geomind.types import Message, ToolCall

    def checked(case, *calls):
        made = Message(role="assistant", tool_calls=calls)
        messages = [Message(role="user", content=TASK), made]
        return economics_missing(Context(messages=messages, problem=ProblemState(case=case)))

    setting = ToolCall(id="c1", name="set_case", input={})
    asking = ToolCall(id="c2", name="ask_user", input={"question": "economics.capex.drilling ..."})
    assert checked({"name": "c"}, setting) is not None
    assert checked({"name": "c", "economics": "economics.json"}, setting) is None
    assert checked({"name": "c"}, setting, asking) is None
    assert checked({"name": "c"}, ToolCall(id="c3", name="read_case", input={})) is None
    assert checked(None, setting) is None


FOLLOW_UP = (
    "Which values do you want to change, and to what? Name each path and its new value with unit."
)
"""The case lead's text answer after the user chose ``change some`` in the run, as recorded."""


def test_change_some_without_a_follow_up_question_is_refused_once():
    """The run: after ``change some`` the case lead asked for the values in text, never asked."""
    from geomind.agents.case.lead import NO_CHANGES, changes_not_asked
    from geomind.engine import Context
    from geomind.types import Message, ToolCall

    options = ["approve all", "change some", "stop"]
    asked = ToolCall(id="q1", name="ask_user", input={"question": "Missing?", "options": options})
    messages = [
        Message(role="user", content=TASK),
        Message(role="assistant", tool_calls=(asked,)),
        Message(role="tool", content="change some", tool_call_id="q1"),
    ]
    refusal = changes_not_asked(Context(messages=messages))
    assert refusal.startswith(NO_CHANGES) and "without options" in refusal
    agent = CaseLead()
    assert agent.answer_problem(Context(messages=messages)) == refusal
    again = [*messages, Message(role="user", content=refusal)]
    assert changes_not_asked(Context(messages=again)) is None
    follow = ToolCall(id="q2", name="ask_user", input={"question": FOLLOW_UP})
    answered = [
        *messages,
        Message(role="assistant", tool_calls=(follow,)),
        Message(role="tool", content="site.air.pressure: 1.013 bar", tool_call_id="q2"),
    ]
    assert changes_not_asked(Context(messages=answered)) is None


def test_the_air_pressure_comes_from_a_source_or_an_elevation_by_code():
    """Request 32 dropped: geomind asks for the pressure or the elevation; set_case computes ISA."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "asks the user for the air pressure or the site's elevation" in text
    assert '"pressure": {"elevation": {"value": 12, "unit": "m"}}' in text
    assert "Never write a pressure you worked out" in text

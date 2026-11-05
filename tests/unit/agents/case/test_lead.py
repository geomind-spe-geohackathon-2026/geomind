"""The case_lead: sets the case from the project's files and the user's answers."""

from geomind import runtime
from geomind.agents import CaseLead, DesignLead
from tests.unit.agents.structure import check_complete

TOOLS = [
    "geoscientists",
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
    "read_skill",
    "calculate",
    "web_search",
    "read_web_page",
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
    from geomind.context.skills import load_skill

    assert "setting-the-case" in set_case.description
    assert "send only" in " ".join(load_skill("setting-the-case").split())


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
    order = ["the project's files", "the knowledge base:", "`list_mcp`", "only when none"]
    assert [text.index(item) for item in order] == sorted(text.index(item) for item in order)
    assert "ALWAYS, also when the files seem complete" in text
    assert '`read_rag("knowledge/data-economics.csv", rows=..., columns=[...])`' in text
    assert "knowledge/data-economics.csv" in text and "`placeholder`" in text


def test_the_catalogue_is_read_by_the_rows_of_the_missing_keys_only():
    """B6: the case lead read the whole cost catalogue, 55-80k input tokens a step for 21 steps."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "Never read it whole or by pages" in text
    assert '`rows={"path": [each missing key' in text


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
    assert "before and after it with `read_case`" in text and "never from recall" in text


def test_it_reads_once_asks_once_and_copies_digits():
    """Track A: 12 read_stored calls, three questions for the same values, rounded prices."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "never read it again" in text and "Never ask for it again" in text
    assert "digit for digit" in text and "as few `set_case` calls as you can" in text
    assert "Read once only the rows of the keys the case lacks" in text


def test_it_chooses_among_the_catalogue_s_rows_by_their_status():
    """Several catalogue rows per key: sourced, then verified, then one question for the rest.

    A row whose unit the key does not accept never goes in (Sahand's catalogue of 171 rows).
    """
    text = " ".join(CaseLead().prompt.content.split())
    order = ["beats a `placeholder`", "`verified` row beats a `secondary`", "the latest `year`"]
    assert [text.index(item) for item in order] == sorted(text.index(item) for item in order)
    assert "`EUR/W heat` is `EUR/W`" in text and "never goes in: list it as not usable" in text


def test_the_economics_parts_of_gemini_0_6_2_have_their_rules():
    """``opex.per_energy`` only as a whole map, a cap in hours with its capacity, ice storage.

    gemini 0.6.2 asks a price for every producing kind once ``opex.per_energy`` is given, and a
    ``subsidy.cap`` in h/yr without ``capacity`` is ``missing_assumption``.
    """
    text = " ".join(CaseLead().prompt.content.split())
    assert "the map is all or nothing" in text
    assert "puts every `opex.per_energy.*` key in `open`" in text
    assert "a cap in hours needs `capacity`" in text and "never you" in text
    assert (
        "`capex.ice_storage` and `opex.fixed.ice_storage` price an ice store only when given"
        in (text)
    )


def test_a_refused_full_call_is_sent_again_whole():
    """#69: files alone after a refused full call."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "send the SAME full call again" in text and "never a files-only call" in text
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
    row and sets the economics; the checklist and the stop rule name them too. Since QA-177 the
    confirmation question (3) comes before the one ``set_case`` (4).
    """
    text = " ".join(CaseLead().prompt.content.split())
    steps = ["1. `list_files`", "3. The ONE confirmation", "4. After `approve all`: ONE `set_case`"]
    steps += ["5. Economics, REQUIRED"]
    assert [text.index(step) for step in steps] == sorted(text.index(step) for step in steps)
    step = text[text.index("5. Economics") : text.index("6. Step 6 is ONE read_case()")]
    assert "never twice" in step and "ONE `ask_economics` call" in step
    assert "`discount_rate` too" in step and "the row's `id` only" in step
    assert "`currency` and `price_year` are never asked" in step
    assert "the other rows' ids in `others`" in step
    assert "reads them from the knowledge base itself" in step
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


async def test_a_delegated_case_lead_without_economics_is_sent_back_once(monkeypatch):
    """#124: a run that set the case with no economics and asked nothing is refused once.

    The refusal names step 5, also on a text answer; an answer after the refusal ends the run.
    The scripted set_case has no gemini case behind it and is refused, which (QA-268) no longer
    counts as a write, so the test counts every call as the stored case it stands for.
    """
    from geomind.agents.case import lead

    monkeypatch.setattr(lead, "applied_calls", lead.calls_of)
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
    assert "discount_rate included" in refusal.output
    assert "currency" not in refusal.output and "price_year" not in refusal.output


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


def test_the_per_energy_kinds_the_prompt_puts_in_values_each_have_a_catalogue_row():
    """Catalogue batch 3 gave the boiler, electric boiler and heat pump per-energy rows.

    The four kinds the prompt puts in ``values`` each have a sourced row; the chillers none, so
    the prompt names them in ``open``. A row added for a chiller fails here until the rule says so.
    """
    import csv
    from pathlib import Path

    catalogue = Path(__file__).parents[4] / "data" / "knowledge" / "data-economics.csv"
    start = "economics.opex.per_energy."
    kinds = {
        row["path"].removeprefix(start)
        for row in csv.DictReader(catalogue.open())
        if row["path"].startswith(start) and row["status"] != "placeholder" and row["value_2015"]
    }
    assert kinds == {"boiler", "electric_boiler", "heat_pump", "chp"}


def test_the_catalogue_s_currency_and_price_year_are_never_asked():
    """E2E-9: the economics question asked for currency and price year; the catalogue gives both."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "never ask the user for either" in text and "never both" in text


def test_the_reference_rows_and_the_esp_basis_are_named():
    """Catalogue batch 3: ESP rows are per W electric; the waste and erratum rows never go in."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "per W electric (the motor's rating) while the key is per W of shaft power" in text
    assert "`EUR/m3` or `t/m3`" in text and "`discount-rate-pbl-sde-2026-erratum` rows" in text
    assert "never a value nor in `others`" in text


def test_the_air_is_read_from_a_server_and_the_humidity_is_a_fraction():
    """E2E-2: the air values were asked for with a weather server connected.

    The question asks for the location when only it is missing; the humidity is 0-1 (one run's
    hint said 0-100).
    """
    text = " ".join(CaseLead().prompt.content.split())
    assert "the question asks for the location (place or coordinates)" in text
    assert "`relative_humidity` is a fraction 0-1 (0.8, not 80 %)" in text


def test_the_discount_rate_is_the_real_financial_rate_of_the_latest_pbl_advice():
    """After-merge check: a run left ``discount_rate`` open though the catalogue has its rows.

    The catalogue's prices are real (EUR 2015), so the rate is a real one of a financial
    appraisal: the PBL 2025 real row over the 2022 one, the erratum rows never.
    """
    text = " ".join(CaseLead().prompt.content.split())
    assert "`discount_rate` is never open" in text
    assert "a real rate of a project's financial appraisal" in text
    assert "`discount-rate-pbl-sde-2025-geothermal-real`" in text
    assert "over `discount-rate-pbl-sde-2022-geothermal-real`" in text


def test_the_esp_rows_are_electric_and_the_user_decides_the_basis():
    """The ESP rows are per W electric: the question says so with the shaft-power share, as is.

    The share is the research report's (``data-economics.md``, batch 3).
    """
    from pathlib import Path

    text = " ".join(CaseLead().prompt.content.split())
    assert "shaft power is about 0.85 to 0.9 of the electric rating" in text
    assert "never convert the value: the user decides" in text
    notes = Path(__file__).parents[4] / "data" / "knowledge" / "data-economics.md"
    assert "Shaft power is about 0.85 to 0.9 of it" in " ".join(notes.read_text().split())


def test_every_row_keeps_its_status_and_the_filter_waste_row_is_secondary():
    """The 3.87 EUR/kg row is a proxy for filter waste: shown as secondary, never density."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "Cite each row by its `id` only: the tool reads the rest" in text
    assert "`waste-disposal-tfa-france-per-kg-filter-density` (secondary, filter waste only)" in (
        text
    )
    assert "`waste-density-geothermal-filter-nrg-2020`" in text


def test_qa_177_one_question_then_one_set_case_then_one_follow_up():
    """QA-177: converted, plants_need only after set_case; source labels; no calculate."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "merge their findings; save nothing yet" in text
    assert "Group III, brine, gas, air and utilities (`site.fluid.*`, `site.air.*`" in text
    assert "ONE follow-up `ask_user`, only when that `set_case` returns `plants_need`" in text
    assert "put each of those in the ONE confirmation question" not in text
    assert "Show that value" not in text and "never the ISA pressure" in text
    assert "Never use `calculate` for a case value" in text
    assert 'a Knowledge value is `"knowledge"`' in text and '`"connector"`' in text


def test_qa_227_the_case_is_trusted_over_the_brief():
    """QA-227: a brief's claim that differs from read_case is reported, never asked."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "Trust the case over the brief" in text


def test_qa_197_a_stop_must_be_reported_and_qa_198_the_question_says_what_is_stored():
    """QA-197: an answer after stop starts with STOPPED; QA-198: no 'case is set' before it is."""
    from geomind.agents.case.lead import NO_STOP, STOPPED, stop_not_reported
    from geomind.engine import Context
    from geomind.types import Message, ToolCall

    text = " ".join(CaseLead().prompt.content.split())
    assert 'never "the case is set from the files"' in text
    asked = Message(role="assistant", tool_calls=(ToolCall(id="q", name="ask_user", input={}),))
    reply = Message(role="tool", content="stop", tool_call_id="q")

    def answer(text):
        call = ToolCall(id="f", name="finish", input={"answer": text})
        return Message(role="assistant", tool_calls=(call,))

    hidden = [asked, reply, answer("Blocking: no time zone")]
    assert stop_not_reported(Context(messages=hidden)).startswith(NO_STOP)
    told = [asked, reply, answer(f"{STOPPED}: nothing is stored")]
    assert stop_not_reported(Context(messages=told)) is None
    again = [*hidden, Message(role="tool", content=f"{NO_STOP}: ...", tool_call_id="f")]
    assert stop_not_reported(Context(messages=[*again, answer("x")])) is None


def test_qa_243_economics_written_with_set_case_unasked_are_refused_once():
    """QA-243: two refused ask_economics, then economics by set_case; the finish is refused."""
    from geomind.agents.case.lead import BY_HAND, economics_by_hand
    from geomind.engine import Context
    from geomind.types import Message, ToolCall

    ask = ToolCall(id="e", name="ask_economics", input={"values": []})
    write = ToolCall(id="s", name="set_case", input={"economics": {"capex": {}}})
    refused = Message(role="tool", content="ask_economics: row = 'x' is not in", tool_call_id="e")
    messages = [
        Message(role="assistant", tool_calls=(ask,)),
        refused,
        Message(role="assistant", tool_calls=(write,)),
        Message(role="tool", content="{'case': {}}", tool_call_id="s"),
    ]
    assert economics_by_hand(Context(messages=messages)).startswith(BY_HAND)
    answered = Message(role="tool", content="{'answer': 'change some'}", tool_call_id="e")
    assert economics_by_hand(Context(messages=[messages[0], answered, *messages[2:]])) is None
    text = " ".join(CaseLead().prompt.content.split())
    assert "Economics enter the case ONLY through `ask_economics`" in text


def test_qa_268_a_denied_or_refused_set_case_never_makes_the_economics_question_due():
    """QA-268: the user denied a set_case of the analysis period; the guard forced ask_economics."""
    from geomind.agents.case.lead import economics_by_hand, economics_missing
    from geomind.context import ProblemState
    from geomind.engine import Context
    from geomind.types import Message, ToolCall

    write = ToolCall(id="s", name="set_case", input={"economics": {"analysis_period": 30}})
    made = Message(role="assistant", tool_calls=(write,))

    def guards(content):
        messages = [made, Message(role="tool", content=content, tool_call_id="s")]
        context = Context(messages=messages, problem=ProblemState(case={"name": "c"}))
        return economics_by_hand(context), economics_missing(context)

    denied = "Do not change the case; just tell me what the NPV would be at 30 years."
    assert guards(denied) == (None, None)
    assert guards('{"error": {"code": "case_incomplete"}}') == (None, None)
    assert all(guards('{"case": {}, "version": 2}'))


def test_qa_271_the_prompt_stays_short_and_cites_the_handbook_by_section():
    """QA-271: the system prompt went to every call at 42-46k characters, a third of the input."""
    from pathlib import Path

    import geomind

    text = (Path(geomind.__file__).parent / "prompts" / "case" / "lead.md").read_text()
    assert len(text) < 20_000
    assert 'read_rag("knowledge/handbook-case.md", section="<n>")' in " ".join(text.split())


def test_qa_295_a_case_that_lost_an_approved_value_is_refused_once():
    """QA-295: the user approved 25 °C/km and GLR 0.5; set_case stored a document's 30 and 0.8."""
    from geomind.agents.case.lead import NOT_STORED, approved_values_differ
    from geomind.context import ProblemState
    from geomind.engine import Context
    from geomind.types import Message, ToolCall

    question = (
        "Nothing is saved yet.\n"
        "- site.ground.gradient = 25 °C/km | engineering assumption | Norwegian bedrock\n"
        "- site.reservoir.reference_depth = 2000 m | engineering assumption | depth\n"
        "- site.fluid.gas_liquid_ratio = 0.5 Nm3/m3 | engineering assumption | modest\n"
        "- site.ground.surface_temperature = 5 degC | engineering assumption | mean air\n"
    )
    ask = ToolCall(id="q", name="ask_user", input={"question": question})
    messages = [
        Message(role="assistant", tool_calls=(ask,)),
        Message(role="tool", content="approve all", tool_call_id="q"),
    ]
    stored = {
        "site": {
            "ground": {
                "gradient": {"value": 30, "unit": "°C/km"},
                "surface_temperature": {"value": 5, "unit": "degC"},
            },
            "reservoir": {"reference_depth": {"value": 2000, "unit": "m"}},
            "fluid": {"gas_liquid_ratio": {"value": 0.8, "unit": "Nm3/m3"}},
        }
    }
    refusal = approved_values_differ(Context(messages=messages, problem=ProblemState(case=stored)))
    assert refusal.startswith(NOT_STORED)
    assert "site.ground.gradient approved 25 °C/km, stored 30 °C/km" in refusal
    assert "gas_liquid_ratio approved 0.5" in refusal and "reference_depth" not in refusal
    stored["site"]["ground"]["gradient"]["value"] = 25
    stored["site"]["fluid"]["gas_liquid_ratio"]["value"] = 0.5
    assert (
        approved_values_differ(Context(messages=messages, problem=ProblemState(case=stored)))
        is None
    )
    again = [*messages, Message(role="tool", content=f"{NOT_STORED}: ...", tool_call_id="f")]
    assert approved_values_differ(Context(messages=again, problem=ProblemState(case={}))) is None

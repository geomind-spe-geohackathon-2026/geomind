"""The project lead: plans the teams' work, routes failures, decides the end."""

import re

from geomind import runtime
from geomind.agents import ProjectLead
from geomind.agents.project.review import Review
from geomind.stores import MemoryWorkspace
from tests.fixtures.cases import example_case
from tests.fixtures.runs import call, context, engine_for, of_type, run, says, uses
from tests.unit.agents.structure import check_complete

TOOLS = [
    "case_lead",
    "design_lead",
    "reviewer",
    "analysis_lead",
    "explainer",
    "support_lead",
    "comparison",
    "list_plants",
    "list_studies",
    "list_files",
    "read_case",
    "set_case",
    "adopt_design",
    "case_changes",
    "accept_case",
    "update_state",
    "read_stored",
    "read_knowledge",
    "ask_user",
    "finish",
]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(ProjectLead, "project/lead", TOOLS)


def test_its_reviewer_runs_gemini_s_check_in_code():
    """The reviewer tool is the review with gemini's verdict after it, not a bare delegate."""
    assert isinstance(ProjectLead().tools()["reviewer"], Review)


def test_its_comparison_never_waits_for_a_user():
    """The comparison runs the rule driver with the settings and no user inside it."""
    with runtime.settings(compare_concurrency=2, compare_retries=1):
        driver = ProjectLead().tools()["comparison"].agent
    assert (driver._concurrency, driver._retries, driver._asks) == (2, 1, False)


def test_its_prompt_plans_routes_and_stops():
    """Order of the teams, briefs, owners, one question, never loosening, the stop rules."""
    text = ProjectLead().prompt.content
    order = [
        "(`case_lead`)",
        "(`design_lead`",
        "(`reviewer`)",
        "(`analysis_lead`)",
        "(`explainer`)",
    ]
    assert [text.index(item) for item in order] == sorted(text.index(item) for item in order)
    for words in ("Never loosen the case", "one question with options", "repeated_failure"):
        assert words in text
    rules = text.split("## Rules")[1].split("## Output")[0]
    assert not re.search(r"\d", re.sub(r"`[^`]*`", "", rules))


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_PROJECTLEAD_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_PROJECTLEAD_MODEL", raising=False)
    assert runtime.role_models()["projectlead"] is None
    assert "GEOMIND_PROJECTLEAD_MODEL" in runtime.missing_model_settings()


async def test_the_project_s_case_file_is_loaded_by_rule_first():
    """With a project case and no case in the state, the first move is code, not the model."""
    workspace = MemoryWorkspace(cases={"p": example_case("hackathon_2026")})
    engine = engine_for([says("planned")], workspace=workspace)
    start = context(project="p")
    result = await engine.run(ProjectLead(), start)
    events = engine.store.load_events(start.run_id)
    calls = [event for event in of_type(events, "tool.started") if event.agent == "project_lead"]
    assert calls[0].tool == "set_case" and calls[0].input == {"source": "project"}
    assert result.answer == "planned"


async def test_without_a_project_case_the_model_plans_from_the_start():
    """No case file: the model's first call is its own."""
    script = [uses(call("update_state", "u", changes=[])), says("done")]
    _, _, events = await run(script, agent=ProjectLead())
    first = of_type(events, "tool.started")[0]
    assert first.tool == "update_state"


def test_a_case_change_the_user_confirmed_is_accepted_not_asked_again():
    """#53: the case lead's question was approved, then the project lead asked the same again."""
    text = ProjectLead().prompt.content
    assert "already confirmed through the case lead" in text and "never ask again" in text


def test_qa_227_a_read_case_before_set_case_is_stale():
    """QA-227: a case saved by hand is approved; an earlier read_case is stale."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "A case the user saved by hand" in text
    assert "Each `read_case` result from before a `set_case` is stale" in text


def test_qa_197_a_stop_to_the_case_lead_ends_the_request_by_rule():
    """QA-197: the case lead's STOPPED answer ends the request; no team is sent again."""
    from geomind.agents.case.lead import STOPPED
    from geomind.agents.project.lead import case_stopped
    from geomind.types import Message, ToolCall

    sent = ToolCall(id="c", name="case_lead", input={"task": "set the case"})
    stopped = f"{STOPPED}: nothing is stored."
    messages = [
        Message(role="user", content="Build the case"),
        Message(role="assistant", tool_calls=(sent,)),
        Message(role="tool", content=stopped, tool_call_id="c"),
    ]
    assert case_stopped(messages) == stopped
    assert (
        case_stopped([*messages[:2], Message(role="tool", content="Case set.", tool_call_id="c")])
        is None
    )
    text = " ".join(ProjectLead().prompt.content.split())
    assert "A user's `stop` to a team's question ends the request" in text


def test_qa_229_257_187_245_only_what_the_request_asks():
    """QA-229, QA-257: no unasked study; QA-187: no review of the structure; QA-245: case change."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "Do what the request asks and nothing more" in text
    assert "No brief widens the request" in text
    assert "never for an engineering review" in text
    assert "After a case change, the design team's brief is" in text


def test_qa_283_an_empty_project_asks_for_the_site_first():
    """QA-283: no files and no case: ask the site and demand, never brief from a missing file."""
    lead = ProjectLead()
    assert "list_files" in lead.tools()
    text = " ".join(lead.prompt.content.split())
    assert "In an empty project (no files, no case), ask the user first" in text
    assert "is that case's brief only when the user or the project's files name that case" in text


def test_qa_288_a_denied_card_reaches_the_project_lead_with_the_user_s_words():
    """QA-288: a nested set_ranges denial with words is shown to the project lead."""
    from geomind.agents.project.lead import DENIALS, denials_note

    note = denials_note([("set_ranges", "Search ranges on design/v1", "Do not search the plant.")])
    assert note.startswith(DENIALS) and "Do not search the plant." in note
    assert denials_note([]) is None
    text = " ".join(ProjectLead().prompt.content.split())
    assert "A card the user denied is the user's instruction for this request" in text


def test_qa_289_an_earlier_answer_is_not_printed_again():
    """QA-289: a short comparison re-printed the whole earlier report; refused once."""
    from geomind.agents.project.lead import REPEATED, earlier_answer_repeated
    from geomind.engine import Context
    from geomind.types import Message, ToolCall

    report = "\n".join(
        f"Module {n}: a line of the earlier design report, long enough." for n in range(30)
    )

    def answered(text):
        finish = ToolCall(id="f", name="finish", input={"answer": text})
        return [
            Message(role="user", content="Write the report."),
            Message(role="assistant", content=report),
            Message(role="user", content="Compare the two versions in a short form."),
            Message(role="assistant", tool_calls=(finish,)),
        ]

    assert earlier_answer_repeated(Context(messages=answered(report + "\n| v1 | v2 |"))).startswith(
        REPEATED
    )
    assert earlier_answer_repeated(Context(messages=answered("| v1 | v2 |\nBuild v1."))) is None
    text = " ".join(ProjectLead().prompt.content.split())
    assert "An earlier answer of this chat is never printed again" in text


def test_qa_224_a_saved_case_is_loaded_by_rule_and_never_again_as_a_no_op():
    """QA-224: the load card came back for a case equal to the chat's."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "The run loads a saved case that differs from the chat's by rule" in text
    assert "(a card that changes nothing)" in text


def test_qa_179_an_optimisation_answer_comes_from_the_study_record():
    """QA-179: the analysis lead and explainer are briefed at once, with the study key."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "After an optimisation, the study record holds the answer" in text


def test_qa_211_a_failed_requirement_is_met_by_design_changes():
    """QA-211: design changes only, never accepting the failure or changing the requirement."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "The question offers design changes only" in text
    assert "accept the design with the open requirement" not in text


def test_qa_309_a_knowledge_case_is_offered_only_when_it_is_whole():
    """QA-309: a brief or an assumptions document alone is no case to offer."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "with the option to upload the files of a case" in text
    assert "a brief or an assumptions document alone is no case" in text


def test_qa_269_an_explanation_of_a_stored_result_goes_to_the_explainer():
    """QA-269: how much, why this unit, is X consistent: the explainer, never analysis_lead."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "goes to the explainer, never to analysis_lead" in text


def test_qa_312_making_a_design_the_project_plant_is_one_adopt_design():
    """QA-312: the design lead adopts it with one call and does nothing else."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "goes to the design lead as one `adopt_design` call; no other work" in text


def test_qa_333_a_case_loaded_by_rule_is_checked_before_one_explainer_call():
    """QA-333: three explainer runs and a late re-simulate for a five-bullet summary."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "So decide first, before any explainer" in text
    assert "Never brief the explainer twice with the same brief" in text


def test_qa_276_an_optimisation_ends_with_the_best_of_the_plant_asked_for():
    """QA-276: 32 min building an unasked heat-pump family after the optimise answer."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "never brief the design team again for another family the user did not name" in text
    assert "the answer keeps the stored plant and says so" in text


def test_qa_337_a_report_on_several_plant_versions_compares_them_first():
    """QA-337: the report recommended `current` alone while another version ranked first."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "first asks the design lead for one comparison of every version" in text
    assert "never `current` alone" in text


def test_qa_347_could_a_variant_be_simulated_is_a_comparison_for_the_design_lead():
    """QA-347: 'could the compression option be simulated' went to the analysis lead alone."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "A question that asks whether a variant could be simulated or compared" in text
    assert "`design change needed: <variant>: <why>`" in text


def test_qa_349_economics_left_open_are_finished_work():
    """QA-349: keys no source gives are named open, never delegated again."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "Keys ask_economics left open because no source gives them" in text
    assert "never ask the case lead to fill them with guesses" in text


def test_qa_351_long_knowledge_documents_are_read_by_section():
    """QA-351: contents first, then sections; never a handbook whole."""
    from geomind.agents import AnalysisLead, Explainer, Reviewer

    for agent in (ProjectLead(), Explainer(), Reviewer(), AnalysisLead()):
        text = " ".join(agent.prompt.content.split())
        assert "contents first" in text and "never the whole document" in text, agent.name


def test_qa_351_a_brief_quotes_the_handbook_lines_it_needs():
    """QA-351: members re-read handbook sections their lead had already read."""
    text = " ".join(ProjectLead().prompt.content.split())
    assert "Quote the handbook lines a member needs in its brief, with their section number" in text


async def test_qa_355_an_empty_project_gets_its_verified_design_as_first_plant():
    """QA-355: a designed and verified plant stayed in the run store; the project had none."""

    from geomind.agents.project.lead import ADOPT, unsaved_design
    from geomind.context import ProblemState
    from geomind.engine import Context
    from geomind.types import Message, ToolCall
    from tests.fixtures.sessions import StubSession

    class Empty:
        """A project with no plant file and no plant version."""

        def __init__(self, plants=None):
            self._plants = plants or {}

        def plants(self, project_id):
            return self._plants

        def project_designs(self, project_id):
            return {"plants": [], "studies": []}

    problem = ProblemState(
        design={"reference": "design/best", "result": "result/r1"},
        verification={"result": "result/r1", "passed": True},
    )
    reviewed = [Message(role="user", content="Design a plant")]

    def context(workspace, messages=reviewed, state=problem):
        return Context(
            project="p1", session=StubSession(workspace=workspace), problem=state, messages=messages
        )

    assert unsaved_design(context(Empty())) == "design/best"
    assert unsaved_design(context(Empty({"Plant": {}}))) is None
    failed = ProblemState(design=problem.design, verification={"result": "r", "passed": False})
    assert unsaved_design(context(Empty(), state=failed)) is None
    adopted = ToolCall(id=ADOPT, name="adopt_design", input={})
    done = [*reviewed, Message(role="assistant", tool_calls=(adopted,))]
    assert unsaved_design(context(Empty(), messages=done)) is None
    assert "adopt_design" in ProjectLead().tools()

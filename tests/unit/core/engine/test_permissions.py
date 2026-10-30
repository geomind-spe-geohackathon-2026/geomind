"""The permission order, rule by rule, and the modes."""

import pytest

from swarmax.core.engine import Permissions
from swarmax.core.engine.hooks import Hook, RequireApproval
from swarmax.core.engine.permissions import PLAN_FEEDBACK
from swarmax.core.types import Allow, Deny, Request
from swarmax.errors import UnknownNameError
from swarmax.tools import Tool
from tests.fixtures.runs import EXECUTED, call, of_type, run, says, uses


def tool(name="thing", effect="read"):
    """Return a tool with an effect."""
    return Tool(name, "d", {}, print, effect=effect)


READ, WRITE = tool("reader", "read"), tool("writer", "write")
EXECUTE, EXTERNAL = tool("runner", "execute"), tool("caller", "external")
COMPUTE = tool("adder", "compute")


def test_unknown_mode_suggests_a_name():
    """A mode is one of four."""
    with pytest.raises(UnknownNameError, match="did you mean 'readonly'"):
        Permissions(mode="read only")


def test_unknown_effect_rule_raises():
    """An effect rule names a real effect."""
    with pytest.raises(UnknownNameError, match="did you mean 'execute'"):
        Permissions(ask=("effect:excute",))


def test_deny_rule_beats_everything_after_it():
    """A deny wins over ask, allow and the most permissive mode."""
    rules = Permissions(mode="auto", deny=("writer",), ask=("writer",), allow=("writer",))
    decision, rule = rules.decide(WRITE)
    assert isinstance(decision, Deny) and rule == "deny:writer"


def test_deny_rule_by_effect():
    """A rule can name an effect."""
    decision, rule = Permissions(deny=("effect:execute",)).decide(EXECUTE)
    assert isinstance(decision, Deny) and rule == "deny:effect:execute"


def test_ask_rule_beats_allow_rule():
    """Ask comes before allow, and even ``auto`` asks."""
    decision, rule = Permissions(mode="auto", ask=("writer",), allow=("writer",)).decide(WRITE)
    assert isinstance(decision, Request) and rule == "ask:writer"
    assert decision.kind == "approval"


def test_ask_rule_on_a_read_tool_asks():
    """An ask rule is not limited to tools that change something."""
    decision, _ = Permissions(ask=("reader",)).decide(READ)
    assert isinstance(decision, Request)


def test_hook_ask_rules_join_the_rule_list():
    """``RequireApproval`` adds ask rules."""
    decision, rule = Permissions().decide(READ, ask=RequireApproval(["reader"]).ask_rules)
    assert isinstance(decision, Request) and rule == "ask:reader"


def test_allow_rule_skips_the_question_in_ask_mode():
    """The reason allow rules come before the mode."""
    decision, rule = Permissions(allow=("writer",)).decide(WRITE)
    assert isinstance(decision, Allow) and rule == "allow:writer"


def test_allow_rule_by_effect():
    """An allow rule can name an effect."""
    decision, _ = Permissions(allow=("effect:external",)).decide(EXTERNAL)
    assert isinstance(decision, Allow)


@pytest.mark.parametrize("item", [READ, COMPUTE])
def test_ask_mode_lets_read_and_compute_through(item):
    """Nothing changes, nothing to ask."""
    decision, rule = Permissions().decide(item)
    assert isinstance(decision, Allow) and rule == "mode:ask"


@pytest.mark.parametrize("item", [WRITE, EXECUTE, EXTERNAL])
def test_ask_mode_asks_for_the_rest(item):
    """Everything that changes something asks."""
    decision, rule = Permissions().decide(item)
    assert isinstance(decision, Request) and rule == "mode:ask"


@pytest.mark.parametrize("item", [READ, COMPUTE, WRITE, EXECUTE, EXTERNAL])
def test_auto_mode_allows_all(item):
    """Without rules ``auto`` never asks."""
    decision, rule = Permissions(mode="auto").decide(item)
    assert isinstance(decision, Allow) and rule == "mode:auto"


@pytest.mark.parametrize("item", [READ, COMPUTE])
def test_readonly_allows_read_and_compute(item):
    """Reading stays possible."""
    assert isinstance(Permissions(mode="readonly").decide(item)[0], Allow)


@pytest.mark.parametrize("item", [WRITE, EXECUTE, EXTERNAL])
def test_readonly_denies_the_rest(item):
    """Nothing changes in ``readonly``."""
    decision, rule = Permissions(mode="readonly").decide(item)
    assert isinstance(decision, Deny) and rule == "mode:readonly"


@pytest.mark.parametrize("item", [READ, COMPUTE, WRITE, EXECUTE, EXTERNAL])
def test_plan_runs_no_tool(item):
    """``plan`` feeds back what to do instead."""
    decision, rule = Permissions(mode="plan").decide(item)
    assert decision == Deny(reason=PLAN_FEEDBACK) and rule == "mode:plan"


def test_allow_rule_cannot_override_readonly_or_plan():
    """A restricted mode holds against an allow rule."""
    for mode in ("readonly", "plan"):
        assert isinstance(Permissions(mode=mode, allow=("writer",)).decide(WRITE)[0], Deny)


def test_ask_rule_cannot_open_readonly_or_plan():
    """An approval could otherwise run a write tool in a restricted mode."""
    for mode in ("readonly", "plan"):
        assert isinstance(Permissions(mode=mode, ask=("writer",)).decide(WRITE)[0], Deny)


async def test_every_decision_names_its_rule_in_the_log():
    """The log shows why each tool ran."""
    permissions = Permissions(allow=("save_note",))
    _, _, events = await run([uses(call("save_note", text="x")), says()], permissions=permissions)
    decision = of_type(events, "permission")[0]
    assert (decision.decision, decision.rule, decision.tool) == (
        "allow",
        "allow:save_note",
        "save_note",
    )


async def test_hooks_come_first():
    """A hook's denial needs no rule."""

    class No(Hook):
        def before_tool_call(self, agent, call):
            return Deny(reason="hook says no")

    _, _, events = await run(
        [uses(call("lookup", key="k")), says()], hooks=[No()], permissions=Permissions("auto")
    )
    assert of_type(events, "permission")[0].rule == "hook:No"


@pytest.mark.parametrize("mode", ["readonly", "plan"])
async def test_restricted_modes_run_no_write_or_execute_tool(mode, tmp_path):
    """Both modes hold end to end, and the model reads why."""
    script = [
        uses(call("save_note", "a", text="x"), call("run_python", "b", code="print(1)")),
        says("understood"),
    ]
    result, _, events = await run(script, permissions=Permissions(mode=mode))
    assert result.answer == "understood" and EXECUTED == []
    calls = [event for event in of_type(events, "tool.result") if event.call_id]
    assert len(calls) == 2 and all(event.is_error for event in calls)
    assert "tool.started" not in [event.type for event in events]


async def test_plan_mode_feeds_back():
    """The model reads the instruction of the mode."""
    _, _, events = await run(
        [uses(call("lookup", key="k")), says()], permissions=Permissions(mode="plan")
    )
    assert of_type(events, "tool.result")[0].output == PLAN_FEEDBACK

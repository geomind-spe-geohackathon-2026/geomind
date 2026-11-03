"""The scripted model of ``alternatives/three_families``: its moves are code, every tool is real.

Usage::

    python -m evals.scripted --recording evals/recordings/alternatives/three_families.jsonl

It runs the task through the ``CompareLoop`` offline, with gemini's real tools, and writes each
completion it gave to the recording, which ``FakeLLM.from_recording`` replays. NOTE: the moves
read the role from the task and the system prompt and the next step from the tools' results, so a
change of a tool's output gives a new recording, never invented numbers.
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

from evals import run as evals
from geomind.providers import Recorder
from geomind.types import Completion, ToolCall, Usage

TASK = evals.ROOT / "tasks" / "alternatives" / "three_families.yaml"
FAMILIES = {
    "heat_only": "HeatingPlant",
    "chiller": "HeatingCoolingPlant",
    "heat_pump": "HeatingHeatPumpCoolingPlant",
}
SEARCH = {"objective": "lcts", "evaluations": 20, "seed": 0}
FAMILY_TASK = re.compile(r"Design one alternative only: (\w+):")


def parsed(content):
    """Return a tool result as data: JSON, a Python literal, or the text itself."""
    try:
        return json.loads(content)
    except (TypeError, ValueError):
        pass
    try:
        return ast.literal_eval(content)
    except (ValueError, SyntaxError):
        return content


def results(messages):
    """Return the tool results of the conversation, oldest first."""
    return [parsed(item.content) for item in messages if item.role == "tool"]


def made_calls(messages):
    """Return the tool calls the model made in the conversation, oldest first."""
    return [call for item in messages if item.role == "assistant" for call in item.tool_calls]


def last_input(made, name, field):
    """Return ``field`` of the input of the last call of tool ``name``."""
    return next(call.input[field] for call in reversed(made) if call.name == name)


def calls(*items, text=""):
    """Return a completion that calls each ``(tool, input)`` of ``items``."""
    tool_calls = tuple(
        ToolCall(id=f"c{number}_{name}", name=name, input=data)
        for number, (name, data) in enumerate(items)
    )
    return Completion(text=text, tool_calls=tool_calls, usage=Usage(), model="scripted")


def say(text):
    """Return a completion that answers with ``finish``."""
    return calls(("finish", {"answer": text}))


def plan(turn):
    """Return the planning designer's move: the plants and the case, then the families."""
    if turn == 0:
        return calls(("list_plants", {}), ("set_case", {"source": "project"}))
    if turn > 1:
        return say("Planned three families from the project's plants.")
    families = [
        {"id": key, "summary": f"the project's {plant}", "status": "open"}
        for key, plant in FAMILIES.items()
    ]
    changes = [
        {"op": "add", "path": "/design/families", "value": families},
        {"op": "add", "path": "/design/search", "value": SEARCH},
    ]
    return calls(("update_state", {"changes": changes}))


def entry(key, design, result, check):
    """Return the move that records a family's alternative from gemini's check."""
    feasible = bool(check.get("feasible"))
    messages = "; ".join(item.get("message", "") for item in check.get("reasons", []))
    reason = None if feasible else messages or "gemini found it infeasible"
    verdict = "feasible" if feasible else "infeasible"
    value = {"family": key, "design": design, "result": result, "verdict": verdict}
    change = {"op": "add", "path": "/design/alternatives/-", "value": {**value, "reason": reason}}
    return calls(("update_state", {"changes": [change]}))


def after_check(key, out, made):
    """Return the move after a check: optimise a feasible sized design, else record it."""
    recorded = (
        last_input(made, "simulate", "design"),
        last_input(made, "check_results", "reference"),
    )
    if any(call.name == "optimize" for call in made) or not out.get("feasible"):
        return entry(key, *recorded, out)
    search = {name: SEARCH[name] for name in ("objective", "evaluations", "seed")}
    return calls(("optimize", {"design": f"design/{key}_sized", "name": f"{key}_best", **search}))


def after_optimize(key, out, made):
    """Return the move after a search: simulate the best, or keep the sized design."""
    if isinstance(out, dict) and "error" not in out:
        return calls(("simulate", {"design": f"design/{key}_best"}))
    first = next(call.input["reference"] for call in made if call.name == "check_results")
    return entry(key, f"design/{key}_sized", first, {"feasible": True})


def family(key, messages):
    """Return a family run's next move from its last call and what it returned."""
    made = made_calls(messages)
    done = results(messages)
    out = done[-1] if done else None
    last = made[-1].name if made else None
    moves = {
        None: lambda: calls(("read_plant", {"project_plant": FAMILIES[key]})),
        "read_plant": lambda: calls(
            ("build_plant", {"plant": out["plant"], "name": f"{key}_start"})
        ),
        "build_plant": lambda: calls(
            ("size_plant", {"design": f"design/{key}_start", "name": f"{key}_sized"})
        ),
        "size_plant": lambda: calls(("simulate", {"design": f"design/{key}_sized"})),
        "simulate": lambda: calls(("check_results", {"reference": out["reference"]})),
        "check_results": lambda: after_check(key, out, made),
        "optimize": lambda: after_optimize(key, out, made),
    }
    return moves.get(last, lambda: say(f"{key}: recorded."))()


def verifier(task, turn, done):
    """Return the verifier's move: check the result named in the task, then record it."""
    result = re.search(r"result/\w+", task).group(0)
    if turn == 0:
        return calls(("check_results", {"reference": result}))
    if turn > 1:
        return say("checked")
    value = {"result": result, "passed": bool(done[-1].get("feasible"))}
    return calls(
        ("update_state", {"changes": [{"op": "add", "path": "/verification", "value": value}]})
    )


def economist(task, turn, done):
    """Return the economist's move: compare the verified results, then record the ranking."""
    if turn == 0:
        references = re.findall(r"result/\w+", task)
        return calls(("compare", {"references": references, "by": ["lcts", "co2"]}))
    if turn > 1:
        return say("compared")
    family_of = {result: name for name, result in re.findall(r"(\w+) (result/\w+)", task)}
    ranked = sorted(done[-1], key=lambda item: item["ranks"]["lcts"])
    ranking = [
        {
            "family": family_of.get(item["reference"]),
            "rank": item["ranks"]["lcts"],
            "pareto": item.get("pareto"),
        }
        for item in ranked
    ]
    best = next((item["family"] for item in ranking if item["family"]), None)
    value = {"by": ["lcts", "co2"], "ranking": ranking, "recommended": best}
    return calls(
        ("update_state", {"changes": [{"op": "add", "path": "/design/comparison", "value": value}]})
    )


def explainer(task):
    """Return the explainer's answer: the table of every family and the comparison."""
    table = task.split("Every family:")[1].split("The comparison:")[0].strip()
    comparison = task.split("The comparison:")[1].split("\n\n")[0].strip()
    return say(
        f"Every family, from gemini's checks:\n\n{table}\n\nThe ranking and the recommendation: "
        f"{comparison}"
    )


class ComparePolicy:
    """Choose each move from the role the task and the system prompt give, as an LLM would."""

    async def complete(self, messages, tools, *, model, settings, on_text=None, **_):
        """Return the next move of the run these messages belong to."""
        system = messages[0].content if messages and messages[0].role == "system" else ""
        task = next(item.content for item in messages if item.role == "user")
        turn = sum(item.role == "assistant" for item in messages)
        found = FAMILY_TASK.search(task)
        if "Plan a comparison" in task or "build nothing yet" in task:
            return plan(turn)
        if found:
            return family(found.group(1), messages)
        if "You are the verifier" in system or task.startswith("Verify "):
            return verifier(task, turn, results(messages))
        if "Compare the verified designs" in task:
            return economist(task, turn, results(messages))
        if "Write the comparison" in task:
            return explainer(task)
        return say("done")


def record(recording, task=TASK):
    """Write the recording of the task anew from the scripted model; return the outcome."""
    Path(recording).unlink(missing_ok=True)
    llm = Recorder(ComparePolicy(), Path(recording))
    return evals.run_task(
        Path(task).stem, evals.load_task(Path(task)), "alternatives", llm, "compare"
    )


def main(argv=None):
    """Write the recording and print the problems of the run; nonzero when there are any."""
    parser = argparse.ArgumentParser(prog="evals.scripted", description=__doc__)
    parser.add_argument("--recording", required=True)
    args = parser.parse_args(argv)
    outcome = record(args.recording)
    print(f"{outcome.name}: {len(outcome.problems)} problems {outcome.problems}")
    return 1 if outcome.problems else 0


if __name__ == "__main__":
    sys.exit(main())

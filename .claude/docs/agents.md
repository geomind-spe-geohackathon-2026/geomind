# Agents

An `Agent` is to one decision what a gemini `Module` is to one tick: it turns a context into an
action and never loops by itself. See `geomind/agents/agent.py`.

```python
class Assistant(gd.Agent):
    """General assistant that answers with the tools it has."""

    def __init__(self):
        super().__init__()

        # Prompt
        self.prompt = gd.Prompt("assistant")

        # Tools
        self.ask_user = gd.tools.ask_user
        self.finish = gd.tools.finish

        # Output
        self.output = gd.Output(str)

        # Model
        self.model = gd.Model(temperature=0)
```

## Declarations

Sections are `# Agents`, `# Prompt`, `# Tools`, `# Output`, `# Model`, in that order, with empty
ones omitted, in `__init__` after `super().__init__()`. `Agent.__setattr__` registers: a
`Tool` under its attribute name, an `Agent` as a child with a dotted `path`, and a `Prompt`,
`Output` or `Model` in its slot. A declaration before `super().__init__()`, a taken name (a method name included) or a value
that is no declaration raises `DeclarationError`, with a close match where there is one. Private
`_names` are plain attributes.

Listings: `tools(recurse=False)`, `children()`, `named_agents()`, `name`, `path`, `tool_schemas()`
and `Agent.help()`.

Rules: declare after `super().__init__()`, and there is no `Team` and no agent container: the order
of agents is a policy, and policies are [loops](engine.md#loops).

A run gets its agent from the routing tables in `geomind/run.py`; see
[Shipped agents](#shipped-agents).

## Calling

`async def forward(self, context) -> Action` renders the context and awaits `self.complete`.
Its signature is exactly that. Override it only for a rule-based step; the engine logs its action as
a completion of the model `rule`. `self.complete(context, messages)` calls the LLM of the run with this agent's model and
tools. The run is passed explicitly: `context.session` is the session of the run, and a context
outside a run raises `RunError`. An agent declares *which model*; the run supplies *which
provider*, so agents stay free of keys and HTTP.

`await agent(context)` returns `AgentResult(action, messages, usage, duration, decision)`. The
order is `before_llm_call` hooks → `forward` → `on_llm_call` callbacks. `decision` is set when a
hook stopped the call, and then `action` is `None`. Agent code never constructs an `AgentResult`.

## Prompt, Model, Output

`Prompt("design/lead")` loads `geomind/prompts/design/lead.md`: a role has one file,
`geomind/prompts/<team>/<name>.md`, as its agent is `geomind/agents/<team>/<name>.py`. Skills stay in
`geomind/prompts/skills/`. `Prompt.text(...)` holds inline text. A role file has the headings
Role, Inputs, Tools, Rules, Output and Examples, and holds engineering method only: every number
comes from the case, the files, knowledge with its source, or a gemini tool.

`Model(name=None, setting=None, temperature=0, max_tokens=None, fallbacks=())`: `setting` names the
role setting in `gd.runtime`, such as `designlead_model`, set by `GEOMIND_DESIGNLEAD_MODEL`. There
is no default model and no fallback from one role to another: a role whose setting is unset has no
model, and a real provider refuses to call. `fallbacks` lists models tried in order when the
provider keeps failing.

`Output(kind=str, max_retries=2)` is the type of the final answer, `str` or a Pydantic model. The
answer of `finish` or of the last message is validated. A failure goes back to the model as
feedback, up to `max_retries`, then the run fails with `stop_reason="error"`. A typed output adds
its JSON schema to the system prompt.

## Shipped agents

The agents are a geothermal engineering team: one folder per team, each team head is `lead`, and
each agent is `geomind/agents/<team>/<name>.py` with its prompt in `geomind/prompts/<team>/<name>.md`;
the tests mirror it as `tests/unit/agents/<team>/test_<name>.py`. Class names stay whole and the import stays
`gd.agents.<Class>`. Each model agent has its own required model setting,
`GEOMIND_<CLASS>_MODEL` in capitals (`GEOMIND_CASELEAD_MODEL`).

| Agent | Folder | Status | In `AGENTS` of `run.py` |
|---|---|---|---|
| `ProjectLead` | `project/lead.py` | complete; a model: plans case, design, review, analysis and explanation, writes each team a brief, routes each failure to its owner, asks the user only what the teams cannot settle, stops when the review passed and the analysis is done or a failure repeats after a real change; run by `ProjectLoop` (route `project`) | no |
| `Coordinator` | `project/coordinator.py` | complete; answers with a `Route` (`task`, a brief for an app event; `preferences`, the user's way of working, put in the problem state), called by `Run.start` | no |
| `Reviewer` | `project/reviewer.py` | complete (the `Verifier` until 0.4.22); checks the final design once with gemini, reads the knowledge base only, never experience | no |
| `Explainer` | `project/explainer.py` | complete; the explanation, from the state and the tools; reads the knowledge base only, to cite sources | no |
| `CaseLead` | `case/lead.py` | complete (the `Formulator` until 0.4.22); sets the case from the project's files and the user's answers, confirms every value no file gives in one question | no |
| `Geoscientist` | `case/geoscientist.py` | complete; reads the reports whole once and proposes the ground, reservoir, brine and dissolved-gas values to the `CaseLead` (its `geoscientist` tool) as typed `Findings`: each value with page, table, depth, quality and range, the missing ones and the disagreements with both sources; never sets the case, never fills a gap with a typical value | no |
| `DesignLead` | `design/lead.py` | complete (the `Designer` until 0.4.22); sizes, simulates, checks and optimises a design for the case, which it reads and never sets; a comparison runs one per family without `ask_user` | no |
| `ProcessEngineer` | `design/process.py` | complete; chooses the modules for every service of the case, a reason each, builds the skeleton and records `design.modules` and `design.owners` (parameter path prefix to discipline) | no |
| `IntegrationEngineer` | `design/integration.py` | complete; connects the modules: ports, streams, inlets, outlets, fluids, boundaries (the PFD) | no |
| `ReservoirEngineer` | `design/reservoir.py` | complete; doublets, spacing, flow, reservoir cooling, degasser, brine-cooling limit | no |
| `WellEngineer` | `design/well.py` | complete; well depth and path, diameters, the ESP and its setting depth | no |
| `EnergySystemsEngineer` | `design/energy.py` | complete; heat pump, chiller, boiler, storage, exchangers, surface pipes and network | no |
| `AnalysisLead` | `analysis/lead.py` | complete (the `Analyst` until 0.4.22), the sample, with the gemini tools | yes, the default route |
| `Economist` | `analysis/economist.py` | complete; costs, compares, samples uncertainty | no |
| `SupportLead` | `support/lead.py` | complete; takes the other leads' support requests (every lead has `support_lead`), routes each to the summarizer or the curator, checks the answer and sends it back once when wrong | no |
| `Curator` | `support/curator.py` | complete; at the end of a run keeps general per-role lessons and the user's facts in experience with their origin (`write_lesson`); never a design or a number as a rule | no |
| `Summarizer` | `support/summarizer.py` | complete; compaction calls it, and the support lead for a handover summary | no |

The project lead's guards are code: before its first model call it loads the project's case
file by rule (`set_case(source="project")`) when the state has no case; its `reviewer` tool
(`agents/project/review.py`) runs the `Reviewer`, then gemini's verdict (`verify_design`)
on the state, lists each failure with the team it goes to first (a hint by gemini's domain),
flags `repeated_failure` when a changed design fails exactly as before, and keeps a passed design
in experience (`keep_design`); the `Verified` hook of `ProjectLoop` keeps an unverified design
from the user; the budget, the step limit, the output limit and the stop on repeated identical
calls are the engine's. Its `comparison` tool runs the rule-driven `ComparisonDriver`, which
moved with `DesignDriver` and `CompareDriver` to `agents/project/drivers.py` and `agents/project/comparison.py` (`DesignLoop` and
`CompareLoop` still run them alone, and old logs find them by their old paths). The analysis
lead has the `economist` as its member.

The design team works in order: the `DesignLead` asks the `ProcessEngineer`, then the
`IntegrationEngineer`, then the `ReservoirEngineer`, `WellEngineer` and `EnergySystemsEngineer`
in one step, side by side (delegates with `runs_beside` and `limit="design_concurrency"`, at most
`GEOMIND_DESIGN_CONCURRENCY` at once, required, no default), each from the connected design and
each storing its own name; it joins them with `merge_designs`, reviews the plant (every service
and nothing more, sensible connections, coupled values that agree, a source or reason for each
value), sends each problem back to its owner with the reason, and then sizes, simulates, checks
and optimises. An engineer has a `discipline`; `patch_plant` refuses its change to a part
another discipline owns (`design.owners`). Engineers ask nobody: what they cannot settle goes
back to the lead.

Removed in 0.4.22: `Assistant`, `CodeAssistant`, `FamilyDesigner` (a comparison's family run is a
`DesignLead` without `ask_user`), `run_python`, `read_file`, `write_file`, `write_module`,
`test_module` and the code sandbox. No code runs in geomind.

All are exported from `gd.agents`. The skill `designing-a-plant` is general: how to read any case,
choose families, size and optimise, the plant record, and what gemini can and cannot run today, as
facts about gemini. It names no topology and no answer. A skeleton is a real `Agent` with a docstring
stating its job, its prompt file and its model setting, the tools that already exist, and no
`forward`. It constructs and runs, but it knows nothing until someone fills its prompt.

### Tools of each agent

What each agent declares now, and what it gets when it is filled. The second column is the plan, not
frozen; the tools themselves are in [tools.md](tools.md#catalogue). Every agent keeps `ask_user`,
`update_state`, `read_skill` and `finish` when it needs them.

| Agent | Tools |
|---|---|
| `AnalysisLead` | `list_files`, `read_document`, `read_case`, `set_case`, `list_modules`, `describe_module`, `evaluate_module`, `list_plants`, `read_plant`, `list_profiles`, `read_profile`, `save_profile`, `simulate`, `read_result`, `list_studies`, `read_study`, `compute_kpis`, `search_documents`, `update_state`, `read_skill`, `search_memory`, `read_memory`, `search_knowledge`, `ask_user`, `finish` |
| `Coordinator` | none: it answers with a `Route` |
| `Geoscientist` | `list_files`, `read_document`, `search_documents`, `read_case`, `read_stored`, `search_memory`, `read_memory`, `search_knowledge`, `finish` |
| `CaseLead` | `geoscientist`, `list_files`, `read_document`, `search_documents`, `read_case`, `set_case`, `save_profile`, `list_profiles`, `read_profile`, `read_stored`, `search_memory`, `read_memory`, `search_knowledge`, `update_state`, `ask_user`, `finish` |
| `DesignLead` | `process_engineer`, `integration_engineer`, `reservoir_engineer`, `well_engineer`, `energy_systems_engineer`, `merge_designs`, `read_case`, `list_plants`, `read_plant`, `list_modules`, `describe_module`, `evaluate_module`, `build_plant`, `patch_plant`, `set_ranges`, `size_plant`, `list_profiles`, `read_profile`, `simulate`, `read_result`, `list_studies`, `read_study`, `check_results`, `optimize`, `run_study`, `update_state`, `read_skill`, `read_stored`, `search_memory`, `read_memory`, `search_knowledge`, `ask_user`, `finish` |
| `Reviewer` | `check_results`, `case_changes`, `read_case`, `compute_kpis`, `read_result`, `update_state`, `read_skill`, `read_stored`, `search_knowledge`, `finish` |
| `Economist` | `compute_kpis`, `estimate_costs`, `compare`, `run_study`, `sample_uncertainty`, `sensitivity`, `read_result`, `list_studies`, `read_study`, `update_state`, `read_skill`, `read_stored`, `search_memory`, `read_memory`, `search_knowledge`, `finish` |
| `Explainer` | `read_case`, `case_changes`, `read_plant`, `read_result`, `list_studies`, `read_study`, `compute_kpis`, `estimate_costs`, `search_documents`, `search_knowledge`, `finish` |
| `Summarizer` | none |

Package code holds no engineering default; an agent's decision is not a default. The DesignLead
starts from a project plant when `list_plants` has `project_plants` (it builds another only when
none fits, and says why in an assumption). Search ranges are never its choice: they come from the
user or the case, and a missing one is asked with `ask_user` (recorded in `questions`). It also
chooses the backup policy (`params.backup` of the plant), the objective, the ranges and options, the
evaluations and the seed when the request gives none, and the Economist the `samples` and seed, each recorded as an assumption with `source:
agent`, `confirmed: false` and a one-line reason, which the Reviewer and the Explainer report. The
DesignLead records the sized start's whole-year run as `design.start_result` and any other family it
simulated as `design.alternatives` (`[{family, design, result}]`). With two or more buildable
families it compares them in one `run_study` (`minimize`, `prepare: ["size"]`) and records it as
`design.study` (`{key, designs, method, objective, evaluations, seed, best, runs}`; `key` is the
`study/<name>` the tool stored). Every study gets a name of its own and an answer cites the study key
it relies on; `list_studies` and `read_study` (DesignLead, Economist, AnalysisLead, Explainer) read the
chat's stored studies. The driver names
those results and the study in the Economist's task, which compares only them, and puts the study's
ranked table in the Explainer's task.

The DesignLead optimises directly after its own `check_results`: the search counts only trials that
`gm.evaluate.verdict` calls feasible, so no Reviewer round comes before it, and when `optimize`
returns `feasible: false` the DesignLead changes the ranges, the options or the topology itself.
The Reviewer calls `check_results` once, on the final design, and reviews what gemini cannot see:
the case changes since the user gave it (`case_changes`), a result that is not the design's whole
year, and the assumptions the user has not confirmed. The driver hands its report to the
Explainer. The verdict is still gemini's, through `verify_design`; on `case_changed` the driver
asks the user to approve the changed case (`accept_case`) or restore theirs.

### Route

`Route` is what `Coordinator` answers, in `geomind/agents/coordination/coordinator.py`: `kind` is
`answer` or `loop`, `answer` the short direct answer of an `answer` route, `loop` a name of `LOOPS`,
and `agent` a name of `AGENTS`. There is no task text: the loop reads the user's message itself,
so nothing the user said is lost in a retelling. `Run.start` calls the coordinator first, as a
nested run logged before the run. `loop_of(route)` in `run.py` builds the loop: an `answer` route
runs the rule agent `Answer`, which gives the route's text. `LOOPS` holds only the loops that are
built (`tool`, `design`, `compare`), so a route never reaches an unbuilt loop; one set by hand that
raises `NotImplementedYet` still ends the run with `stop_reason="not_implemented"`.

## How to add or fill an agent

The analysis lead is the worked example: `geomind/agents/analysis/analysis lead.py` and
`geomind/prompts/analysis/analysis lead.md`.

1. **The folder.** A skeleton has its file already. A new agent goes in
   `geomind/agents/<area>/<name>.py`, exported from `geomind/agents/__init__.py`, with
   `tests/unit/agents/<area>/test_<name>.py`.
2. **The prompt.** `geomind/prompts/<area>/<name>.md`, loaded with `Prompt("<name>")`, with six
   headings in this order: `## Role`, `## Inputs`, `## Tools`, `## Rules`, `## Output`, `## Examples`.
   Name in `## Tools` only tools the agent has; `test_its_prompt_names_only_tools_it_has` shows how to
   check that.
3. **The tools.** Declare them in `# Tools` in the order they matter, and give the agent as few as it
   needs. A tool's `effect` decides who approves it: `read` and `compute` run freely, while `write`,
   `execute` and `external` ask in `ask` mode. See [tools.md](tools.md). An agent that declares
   `read_skill` gets the list of skills in its system prompt, and `update_state` needs no approval.
4. **The model.** `Model(setting="<name>_model")`, with the setting in `geomind/runtime.py`: `None` for
   the default model, or a cheap model for a call that needs no thought.
5. **The routing.** Add one row to `AGENTS` in `geomind/run.py`. A new way of ordering agents is a
   loop, and a row in `LOOPS`.
6. **Test it by hand.** `geomind chat --agent <name> --live`; see [api.md](api.md#command-line).
7. **Test it by tasks.** Write `evals/tasks/<name>/<task>.yaml` and run
   `python -m evals.run --agent <name> --live` once to record it; see [evals.md](evals.md).
8. **Update this table,** and change its status from skeleton to complete.

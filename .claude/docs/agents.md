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

There is no `Team` and no agent container: the order of agents is a policy, and policies are
[loops](engine.md#loops).

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

`Prompt("assistant")` loads `prompts/general/assistant.md`: a role has one file, in the folder of its
area. `Prompt.text(...)` holds inline text.

`Model(name=None, setting=None, temperature=0, max_tokens=None, fallbacks=())`: `setting` names the
role setting in `gd.runtime`, such as `analyst_model`; with neither a name nor a set role, the model is
`default_model`. `fallbacks` lists models tried in order when the provider keeps failing.

`Output(kind=str, max_retries=2)` is the type of the final answer, `str` or a Pydantic model. The
answer of `finish` or of the last message is validated. A failure goes back to the model as
feedback, up to `max_retries`, then the run fails with `stop_reason="error"`. A typed output adds
its JSON schema to the system prompt.

## Shipped agents

| Agent | Folder | Status | In `AGENTS` of `run.py` |
|---|---|---|---|
| `Analyst` | `analysis/` | complete, the sample; its gemini tools are not built yet, see [plan.md](plan.md) | yes, the default |
| `Assistant`, `CodeAssistant` | `general/` | complete; `Run` uses `CodeAssistant` with a sandbox | `code_assistant` |
| `Summarizer` | `general/` | complete; only compaction calls it | no |
| `Coordinator` | `coordination/` | skeleton; declares `Output(Route)`, `Run` does not call it yet | no |
| `Designer` | `design/` | skeleton | no |
| `Verifier` | `verification/` | skeleton | no |
| `Economist` | `economics/` | skeleton | no |
| `Explainer` | `reporting/` | skeleton | no |

All are exported from `gd.agents`. A skeleton is a real `Agent` with a docstring stating its job, its
prompt file and its model setting, the tools that already exist, and no `forward`. It constructs and
runs, but it knows nothing until someone fills its prompt.

## How to add or fill an agent

The analyst is the worked example: `geomind/agents/analysis/analyst.py` and
`geomind/prompts/analysis/analyst.md`.

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

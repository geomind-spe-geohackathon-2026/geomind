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
ones omitted, and only in `__init__` after `super().__init__()`. `Agent.__setattr__` registers: a
`Tool` under its attribute name, an `Agent` as a child with a dotted `path`, and a `Prompt`,
`Output` or `Model` in its slot. A wrong place, a taken name (a method name included) or a value
that is no declaration raises `DeclarationError`, with a close match where there is one. Private
`_names` are plain attributes.

Listings: `tools(recurse=False)`, `children()`, `named_agents()`, `name`, `path`, `tool_schemas()`
and `Agent.help()`.

There is no `Team` and no agent container: the order of agents is a policy, and policies are
[loops](engine.md#loops).

## Calling

`async def forward(self, context) -> Action` renders the context and awaits `self.complete`.
Override it only for a rule-based step; the engine logs its action as a completion of the model
`rule`. `self.complete(messages)` calls the LLM of the active run with this agent's model and
tools, and raises `RunError` outside a run.

`await agent(context)` returns `AgentResult(action, messages, usage, duration, decision)`. The
order is `before_llm_call` hooks → `forward` → `on_llm_call` callbacks. `decision` is set when a
hook stopped the call, and then `action` is `None`.

## Prompt, Model, Output

`Prompt("assistant")` loads `prompts/assistant.md`, and `Prompt.text(...)` holds inline text.

`Model(name=None, temperature=0, max_tokens=None, fallbacks=())`: `name=None` means the default
model of `gd.runtime`, and `fallbacks` lists models tried in order when the provider keeps failing.

`Output(kind=str, max_retries=2)` is the type of the final answer, `str` or a Pydantic model. The
answer of `finish` or of the last message is validated. A failure goes back to the model as
feedback, up to `max_retries`, then the run fails with `stop_reason="error"`. A typed output adds
its JSON schema to the system prompt.

## Shipped agents

`gd.agents.Assistant` is the agent of S1. `CodeAssistant` adds `run_python`, `read_file` and
`write_file`; `Run` uses it when a sandbox is configured, so a run without one offers the model no
tool that can only fail.

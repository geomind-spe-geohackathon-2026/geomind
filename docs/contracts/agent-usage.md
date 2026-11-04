# Contract: per-agent context and usage (geomind 0.4.24)

geomind 2026-11-04, asked by Sahand at 14:10 UTC. The app shows, for each agent and session:
- the context used and remaining;
- tokens and cost;
- its tool calls;
- a correct run total.

This contract only adds fields. Nothing is removed or renamed. Old logs don't have these fields,
so the frontend shows "n/a" for them.

## Terms
- An agent's **session** is one run of that agent, which is one `run_id`. There is a root run per
  user message and a nested run per delegation. Every event already carries `run_id`, `agent`
  (the path, e.g. `project_lead/design_lead`) and `parent` (the parent run_id, or null).
- A new session starts from its own messages only. Context is counted per session and is never
  summed across sessions or agents.

## Events
- **step.started**, new optional fields:
  - `session: str` (= run_id);
  - `context_window: int | null`, the model's window for this agent.
- **step.finished**, new optional fields:
  - `usage: {input_tokens, output_tokens, cached_tokens, cost}` covers this ONE model call, never a
    running total. `cached_tokens` is part of `input_tokens`.
  - `context: {used, window, remaining}`. `used` is this call's input_tokens; `remaining` = window - used.
- **tool.started / tool.finished**: unchanged; they already carry agent and run_id.
- The **usage** event is the running total of the run tree, unchanged.
- **run.finished**, new optional fields (root run only; null on nested runs):
  - `sessions: [{session, agent, parent, model, steps, tool_calls, usage: {input_tokens,
    output_tokens, cached_tokens, cost}, context: {peak_used, last_used, window}}]`.
  - `agents: [{agent, sessions, steps, tool_calls, usage}]`, the sessions grouped by agent.
  - `total: {input_tokens, output_tokens, cached_tokens, cost, steps, tool_calls}`. It is the sum
    of `sessions`, and each model call is counted once. It equals the last `usage` event.
- **RunResult**: new optional fields `sessions`, `agents` and `total`, with the same shapes.
  `RunResult.usage` stays and equals `total`.

## Example run.finished (root, two sessions)
```json
{"type":"run.finished","run_id":"r1","agent":"project_lead","parent":null,"status":"completed",
 "sessions":[
  {"session":"r1","agent":"project_lead","parent":null,"model":"deepseek/deepseek-v4.1-flash-1017","steps":6,"tool_calls":5,
   "usage":{"input_tokens":41200,"output_tokens":1900,"cached_tokens":30100,"cost":0.0123},
   "context":{"peak_used":9800,"last_used":9800,"window":163840}},
  {"session":"r2","agent":"project_lead/case_lead","parent":"r1","model":"deepseek/deepseek-v4.1-flash-1017","steps":11,"tool_calls":14,
   "usage":{"input_tokens":120500,"output_tokens":4100,"cached_tokens":98000,"cost":0.0311},
   "context":{"peak_used":17400,"last_used":17400,"window":163840}}],
 "agents":[{"agent":"project_lead","sessions":1,"steps":6,"tool_calls":5,"usage":{}},{"agent":"project_lead/case_lead","sessions":1,"steps":11,"tool_calls":14,"usage":{}}],
 "total":{"input_tokens":161700,"output_tokens":6000,"cached_tokens":128100,"cost":0.0434,"steps":17,"tool_calls":19}}
```

## Backend
- Store and stream the new fields as they come (SSE and replay).
- `GET /assistant/runs/{id}/agents` returns one row per session, built from `run.finished.sessions`
  (or live from step events while the run is running): session, parent_session, agent, model,
  tokens, cost, context_used, context_window, context_left and tool_calls. Use geomind's numbers;
  don't compute your own.
- Don't confuse a whole-run cost budget (max_cost, B2) with context: they are separate settings.

## Frontend
- One row per agent session, nested by `parent`:
  - context used / remaining (from the latest `step.finished.context`);
  - input, output and cached tokens;
  - cost;
  - tool calls (list them on expand).
- The run total comes from `total`.
- Never add a parent's numbers to its children's: each session holds its own calls only.

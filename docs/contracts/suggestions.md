# Contract: next-step suggestions in the chat (geomind <-> backend <-> frontend)

Version 5 (v5 23:55: RunResult.suggestions; v4 23:45: project progress from the backend; v3 23:38: stage = project state, stage 5), GEOMIND II, 2026-11-03 23:40 UTC (v2 23:36: backend notes, CONFIRMED by BACKEND I). Asked by Sahand at 23:33 UTC: after each answer the
user sees two or three suggested next steps (for example, after the project is made: "build the
case from my files"; after the case: "design the plant") and can click one.

The change is additive: one optional field on one event, and one new function. Nothing that exists
changes.

## 1. geomind

### 1a. `run.finished` gets an optional `suggestions`

```json
{"type": "run.finished", "status": "completed", "stop_reason": "answered",
 "suggestions": [
   {"label": "Design the plant", "message": "Design a plant for this case."},
   {"label": "Check the case", "message": "Show me the case and the values still without a source."}
 ]}
```

- Only on the root run (`parent` is null), only when `status` is `completed`. Otherwise absent.
- 0 to 3 items. An empty list is left out, like every optional key.
- `label`: what the button shows, at most 40 characters, in the user's language.
- `message`: the text sent as the user's next message when the button is clicked, at most 200
  characters, in the user's language.
- A pending question (`request` event) gets no suggestions: the question's own `options` are the
  buttons there.
- Old logs have none. Readers ignore the key when absent.

- `RunResult.suggestions` (optional) holds the same list, so a caller reads it without the event
  stream (v5, asked by BACKEND I).

### 1b. Where the suggestions come from

- **Code decides the stage** from the problem state, never the model:
  1. no case yet: build the case from the project's files; build it by questions; what files are
     needed;
  2. a case but no plant: design the plant; check the case and its unsourced values; compare
     plant options;
  3. a plant but no study result: optimise the plant; run the economics; check the design;
  4. a study result but no report: write the report; explain the result; a sensitivity study;
  5. everything done (case, plant, study, report): more studies on the same project, e.g. a
     sensitivity or uncertainty study, a structure search (evolve) over other plant options, other
     objectives (cost vs CO2), the design against another case (a colder year, other prices).
- The stage is the PROJECT's state (its files, case, plants, studies and report, across all its
  chats), not one chat's: a new chat in a project that already has a case does not suggest
  building one. A missing input moves the stage back (e.g. the case changed after the study:
  suggest running the study again).
- The project lead may reword or reorder them for the conversation, and may replace one with a
  step that fits the answer better, through its finish (`suggestions` argument). Code checks the
  limits above and that each one is a step the app can run. When the model gives none or a bad
  list, code uses the stage list.
- The labels follow the user's language (Persian when the user writes Persian).

### 1c. `gd.suggest(problem, files) -> [{label, message}]` for an empty chat

- Sync, no LLM call, no cost. `problem` is the chat's problem state (`{}` for a new chat), `files`
  the project's file names (`[]` when none). `language` is taken from the problem state when
  known, otherwise English.
- The backend calls it for a chat with no messages yet, so a new project already shows "build the
  case" buttons before the user types.

### 1d. Project progress (v4, proposed by BACKEND I, chosen by GEOMIND II)

A chat's state has no plants, studies or report, so the stage comes from the backend's project
progress, one shape for both ways in:

```json
{"case":    {"state": "done", "label": "Case 2027"},
 "plant":   {"state": "ready", "label": "HP + compression"},
 "study":   {"state": "empty", "label": ""},
 "results": {"state": "empty", "label": ""},
 "report":  {"state": "empty", "label": ""},
 "case_version": 3, "plant_version": 2, "study_case_version": null,
 "case_changed_after_study": false}
```

- `state` is one of `empty`, `incomplete`, `ready`, `running`, `done`.
- **Inside a run:** a new optional Workspace method `project_state(project_id) -> dict | None`,
  this shape. geomind calls it when the run finishes, for `run.finished.suggestions`. A workspace
  without it, or `None`, falls back to the chat-state rule of 1b.
- **Empty chat:** `gd.suggest(problem, files, project=None)`. The backend passes the same dict as
  `project`. `project=None` falls back to the chat-state rule.
- Stage rules on it: case not `done` -> 1; plant not `done`/`ready` -> 2; study/results not `done`
  -> 3 (`running` -> no "run the study" chip, suggest waiting or explaining); report not `done` ->
  4; all `done` -> 5; `case_changed_after_study` -> suggest running the study again first.
- `incomplete` items get a "finish the ..." suggestion naming its `label`.

## 2. Backend

- Store `suggestions` with the assistant message of the run that produced them, and stream the
  `run.finished` field as it comes (SSE).
- Return `suggestions` (possibly absent) on the assistant message in the chat messages API.
- A new chat has no id yet, so the backend adds `GET /assistant/suggestions?project=<id>[&chat=<id>]`
  -> `{suggestions}` from `gd.suggest(problem, files)` (problem = the chat's state, `{}` when none;
  files = the Library's file names). `GET /assistant/chat/{id}/state` of a chat with no messages
  carries the same list. An error in `gd.suggest` gives `[]`.
- Migration 0014 adds `messages.suggestions`. They stream live and on replay (WS and SSE). The
  backend reads them with getattr, so it still runs on a geomind without them.
- The backend stores `run.finished.suggestions` as geomind sends it and does not filter: geomind
  alone keeps the "root run, completed" rule. (The app's run status is `done`; geomind's
  `run.finished.status` stays `completed`.)
- Implement `Workspace.project_state(project_id)` (1d) and pass the same dict as `project` to
  `gd.suggest`.
- A click is an ordinary `POST` of a user message with the `message` text.

## 3. Frontend

- Show the suggestions of the **last** assistant message only, as clickable chips under it, with
  AI Elements `Suggestion` / `Suggestions` (open source, already the chat's component set). No own
  component.
- Click: send `message` as the user's message (the same path as typing it). The chips disappear
  once the user sends anything.
- Empty chat: show `GET /assistant/suggestions?project=<id>` in the empty state (with `&chat=<id>` once the chat exists).
- Friendly text only; never show internal names.

## 4. Order of work

1. geomind implements 1a-1c with unit tests (no live run needed for the code path; one cheap live
   check of the lead's reworded list).
2. Backend: store, stream, return; empty chat calls `gd.suggest`. Ships with the next backend
   release (the one pinning the geomind release).
3. Frontend: chips; can be built now against the contract with a mock, and deployed after the
   backend.

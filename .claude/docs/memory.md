# Memory and knowledge

Two stores, never mixed (contract v2).

## Knowledge: a shared document base (retrieval)

Documents such as cost catalogues, standards and reports, searched for cited values
(`geomind/stores/knowledge.py`). A document is cut into passages (a PDF by its pages, a text into
paragraphs, a table into runs of rows each with its header), and `search_rag(query)` ranks
them by the words of the query, rarer words counting more: deterministic, no model, no
embedding. Each passage comes as a match of `scope` `knowledge`, with `name` `knowledge/<document>` and its `citation` `{document, title, page}`; `read_rag` reads a
whole document as `knowledge/<name>`. A value taken from knowledge is cited with its document
and page and confirmed by the user before it enters the case, as any value no project file
gives.

A backend gives the knowledge base through the optional `Workspace.knowledge_search(query)`,
`knowledge_files()` and `knowledge_file(name)`; without them the tools answer
`knowledge_unavailable`. The command line reads the folder `GEOMIND_KNOWLEDGE_DIR` (required for
a run with a project, no default) as `FolderKnowledge`. `data/knowledge/cost-sources.csv`, a copy
of gemini's cost catalogue from tag v0.5.13 (see `data/knowledge/cost-sources.md` for its commit
and sha256), is a document of that folder; geomind owns the copy.

## Memory: experience only

`geomind/stores/memory.py`, one section, `experience`:

- designs that passed gemini's check and the reviewer, written by code (`keep_design`, from the
  project lead's review and the design loop), never by a model: the case's general features
  (`FEATURES`, SI units), the sections it set, the design and its result, the KPIs, the verdict,
  the families and the lessons of the rejected rounds, with `origin` `{run, source: code}` and
  `project_id`;
- the curator's lessons and the user's facts, `{id, kind: lesson|user_fact, role, text, origin:
  {run, source}, project_id}` (`write_lesson`; a digit in a lesson is refused).

`search_memory()` returns the past designs at or above `memory_similarity` to the state's case,
each with its score, and the lessons of the caller's role, of `all` and the user's facts;
`read_memory(id)` reads one. The shared prompt section `MEMORY` says a past design is a starting
point: simulate, check and optimise again, and try at least one option that differs from it. The
reviewer and the explainer never read experience. User preferences live in the problem state,
not in memory.

Storage is a protocol (`entries`, `add`): `FileMemory(root)` keeps `<root>/experience.jsonl` for
the command line and `MemoryMemory` holds it in memory. A run picks its memory in
`RunSession.memory` (`geomind/engine/session.py`), in this order:

1. `Engine(memory=...)`, when given;
2. the optional `Workspace.memory(project_id)`, asked once per project and engine: a memory is
   used; `None` is the memory **off** for that project, with no fallback to `GEOMIND_MEMORY_DIR` or
   the folder store (the memory tools and the curator are not offered, nothing is written);
3. a workspace without that method (the command line, `FileWorkspace`, `MemoryWorkspace`):
   `GEOMIND_MEMORY` `on` uses `FileMemory(GEOMIND_MEMORY_DIR)`; `off` or unset is the memory off.

Settings, required, no default: `GEOMIND_MEMORY` (`on` or `off`) decides only case 3, and there
`on` needs `GEOMIND_MEMORY_DIR` (a run without it is refused with an error naming it). A memory
the engine or the workspace gives needs no `GEOMIND_MEMORY_DIR`, and the missing-setting error
never asks for it then. Any memory that is on needs `GEOMIND_MEMORY_SIMILARITY` (0 to 1).
`runtime.memory_settings(source)` lists what each source (`settings`, `store`, `off`) needs.

With the memory off, by either path, no agent, nested or not, is offered `search_memory`,
`read_memory`, `write_lesson` or the curator, and no prompt speaks of the memory: the `MEMORY`
section and the knowledge section's line on memory are left out, and so are the role files' parts
marked `<!-- memory -->` (the design engineers' experience line, the project lead's lessons step,
the support lead's curator). A store that raises answers `memory_unavailable` with its error, never
`internal`, and an experience entry whose features are no numbers scores them as missing.
0.4.22 took a workspace's bound `memory` method itself as the memory, so `search_memory` failed
with `internal` (run c8bf2381); 0.4.23 calls it.
Final and competition runs keep the memory `off`.

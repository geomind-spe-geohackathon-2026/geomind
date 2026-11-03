# Memory and knowledge

Two stores, never mixed (contract v2).

## Knowledge: a shared document base (retrieval)

Documents such as cost catalogues, standards and reports, searched for cited values
(`geomind/stores/knowledge.py`). A document is cut into passages (a PDF by its pages, a text into
paragraphs, a table into runs of rows each with its header), and `search_knowledge(query)` ranks
them by the words of the query, rarer words counting more: deterministic, no model, no
embedding. Each passage is `{id, document, title, page, text, score}`; `rag_read` reads a
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
the command line, `MemoryMemory` holds it in memory, and a backend gives its own as
`Workspace.memory` or `Engine(memory=...)`. Settings, all required, no default: `GEOMIND_MEMORY`
(`on` or `off`); with `on`, `GEOMIND_MEMORY_DIR` and `GEOMIND_MEMORY_SIMILARITY` (0 to 1). Final
and competition runs keep the memory `off`.

# Memory

The agents share one memory with two sections (`geomind/stores/memory.py`).

- `knowledge`: cited reference values. Each entry has `id`, `item`, `value`, `unit`, `title`,
  `publisher`, `year`, `page` or `link`, `price_year` and `currency` for money, `status`
  (`verified`, `secondary`, `placeholder`) and a `note`. A model writes one only with its source
  (`write_memory`); a `placeholder` comes only from a seeded catalogue.
- `experience`, lessons: `{id, kind, role, text, origin: {run, source}}`, `kind` being `lesson`
  (method for one role, by its snake name, or `all`; a digit is refused, so a project's numbers
  never become a rule) or `user_fact` (what the user said about how they work, `source` `user`).
  The `Curator` writes them with `write_lesson` at the end of a run; `search_memory` returns a
  role's lessons, those of `all` and the user's facts as `lessons`; past-design search skips them.
- `experience`, designs: designs that passed verification, written by code (`keep_design` in
  `geomind/tools/memory.py`, called by the project lead's review and by the design loop)
  (`remember_design`), never by a model: the case's general features (`FEATURES`, in SI units:
  heating and cooling peak and mean, supply temperatures, depth, time step), the sections it set,
  the design and its result, the KPIs, the verdict, the families and the lessons of the rejected
  rounds. It holds lessons, not a project's numbers as rules. A replay writes nothing.

Tools (`geomind/tools/memory.py`, shared, so prompts do not list them): the case, design and
analysis teams have `search_memory(query, section=None)`, `read_memory(section, id)` and
`write_memory(entry)`; the reviewer and the explainer have `search_knowledge(query)` and
`read_knowledge(id)`, the knowledge only, never experience, with the prompt section `KNOWLEDGE`. With the
memory off they answer `not_allowed`. `search_memory` finds knowledge by words and experience by
`similarity` to the state's case, only at or above `memory_similarity`, each with its score. The
shared prompt section `MEMORY` says a past design is a starting point: simulate, check and
optimise again, and try at least one option that differs from it. The Reviewer checks from
scratch. The CaseLead searches knowledge before it proposes a value no file gives, and its
confirmation question shows the entry's source and status, a placeholder named as one.

Storage is a protocol (`entries`, `add`): `FileMemory(root)` keeps `<root>/<section>.jsonl` for
the command line, `MemoryMemory` holds it in memory, and a backend gives its own as
`Workspace.memory` or `Engine(memory=...)`. Settings, all required, no default:
`GEOMIND_MEMORY` (`on` or `off`); with `on`, `GEOMIND_MEMORY_DIR` and
`GEOMIND_MEMORY_SIMILARITY` (0 to 1). Final and competition runs keep the memory `off`.

`geomind memory seed FILE` loads a cited catalogue (CSV) into the knowledge. The first is
`data/knowledge/cost-sources.csv`, a copy of gemini's cost catalogue from tag v0.5.13 (see
`data/knowledge/cost-sources.md` for its commit and sha256); geomind owns the copy and reads
nothing of gemini for it.

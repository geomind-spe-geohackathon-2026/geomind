---
name: finding-sources
description: How to find a value in the project's files and the knowledge base: search_rag, read_rag and list_files; arguments and citing.
tools: search_rag, read_rag, list_files, search_knowledge, read_knowledge
roles: all
---

## The tools

### `list_files`

List the files of the project: `files`, each with `name`, `size` and `media_type`.

Read one with `read_rag`, and give a data file to the case with `set_case` `files`.

### `read_rag`

Read a project file, or a document of the knowledge base as `knowledge/<name>`, as text.

A long document with headings (a handbook of 25 to 50 pages with `#`, `##`, `###`) is read by
section, never whole and never page by page from the start. Contents first, then `section=`: a
read without `section` of a document over 12,000 characters gives only its `contents` (each
`{section: "§7.4", title, level, size}`) and a `note`; read next only the sections you need:

- `read_rag(name, outline=true)`: the heading tree, each `{level, number, title, start, size}`
  (`number` is the title's own, such as `3.2`, else its place in the tree).
- `read_rag(name, section="3.2")` or `section="Pumps"` (a title, or a part of one), several at
  once as `section="3.2; 7.4"`: exactly those sections with their subsections, paged with `start` inside it when it is longer than a page; the
  answer names the `section` read. An unknown section is refused with the headings it has.
- A knowledge hit of `search_rag` carries `section`, the heading path it falls in
  (`3 Wells > 3.2 Pumps`): read that whole section next with `section`.

CSV, TSV, JSON, Markdown and text files read as they are, and a PDF as its extracted text with
a `[page n]` marker before each page; another file is a `not_text` error. `start` is the
first character and `length` the number of characters, at most 20,000. Returns `name`,
`start`, `total`, `text` and `next`, where the following page starts (`null` at the
end). The first page of a CSV or TSV also has `table`: `columns`, the number of `rows`,
the `first_rows`, the `last_row` and the `span` its first column covers as a case's
time: `start`, `end` (exclusive, one step after the last row) and `step`, or `null`
when that column is not evenly spaced times. `columns` reads only those columns of a CSV or
TSV, in that order, such as the `id`, `path` and price of a cost table: a wide table costs
far fewer tokens so. `rows` (`{column: [text, ...]}`) reads only the rows whose value in
each named column starts with one of the texts, such as the paths of the keys a case lacks.
A CSV or TSV still longer than 20,000 characters after them gives no `text`: its `table`
outline and a `note`; find its rows with `search_rag` and read them by `rows`. A page
this run already read comes back as `already_read` with a `note` instead of its text: its
text is in the conversation, even with `force`, unless a compaction summarized it since;
after one, `force` reads it again until the whole document was read, then every page is
`already_read` with the references of the stored results. Nested runs share what the run
tree read.

### `search_rag`

Search the project's documents and files and the knowledge base; return `{matches, note}`.

Each match has `scope` (`project` or `knowledge`), `text`, `score` and `citation`,
what a value taken from it is cited with. A project document: `id` and `title`; a passage
of a project file that reads as text, such as a PDF: `name` and `start` for `read_rag`,
cited with its `file` and `page`; a passage of the knowledge base: `name` as
`knowledge/<document>` for `read_rag`, cited with its `document`, `title` and
`page`. The best of each scope come first, in turn. A file's name alone matches nothing. No
match means neither states these words, and the `note` says what to do instead; the same
words again are noted too. A value from the knowledge base goes into the case only after the
user confirms it, as any value no project file gives.

### `search_knowledge`

Search the global Knowledge base only (never the project's files); returns `{matches}`, each
with `name` (`knowledge/<name>`), `text`, `score`, `citation` and its `section` when it has
one. For a team's sub-agent: the lead gives you the project's text; the Knowledge base is yours
to search for what that text lacks.

### `read_knowledge`

Read one Knowledge document by its contents first, then by section: `read_knowledge(name=
"knowledge/<name>")` of a long handbook gives its `contents` only (never its whole text, also
with `whole=true`); `section="10.2"` (a title or a word of one; several as `"10.2; 12.1"`)
reads only those sections, `start` and `length` a window inside one. A name
outside `knowledge/` is refused: project files are the lead's to read.

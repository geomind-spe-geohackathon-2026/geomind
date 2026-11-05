---
name: web-search
description: How to find a missing value on the web with `web_search` and `read_web_page`, and get it approved with its source before anyone uses it.
tools: web_search, read_web_page
roles: all
---

Look in this order: the user's files, the Knowledge base (`search_rag`), the connectors (MCP),
then the web. The web is for what none of them gives: a price, a property, a standard, a site
fact.

Searching:

- `web_search(query, limit)`: short, specific queries with the quantity, the place and the year,
  such as `geothermal doublet drilling cost per metre Netherlands 2020`. A result (title, url,
  snippet, engine, date) is a lead, never a source: a snippet can be cut or wrong.
- Prefer primary sources: agencies, operators, standards bodies, peer-reviewed papers, official
  statistics. Avoid forums, ads and pages that give no source of their own.

Reading:

- `read_web_page(url)` returns the page's main text with `url`, `title`, `publisher`, `author` and
  `date` when the page states them. A long page comes in parts: call again with `start` set to
  `next_start`. PDFs come with `[page N]` marks; cite the page.
- Pages only on the public internet; no login, no forms, no scripts.

Using a value:

- A value from the web is never used, entered in the case or passed to `calculate` until the user
  approves it. Ask in one question with the value, its unit, and its source: URL, publisher, the
  year of the source and the currency year of a price, the page, and a short quote.
- Once approved, record it as a confirmed assumption with that citation (source `user` once they
  approve); then `calculate` and `run_python` can reference it as `{"assumption": "<id>"}`.
- Never convert a price's currency or year yourself; say what the source gives and ask.

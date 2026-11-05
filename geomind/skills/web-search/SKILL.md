---
name: web-search
description: How to find a missing value on the web with `web_search` and `read_web_page`, and get it approved with its source before anyone uses it.
tools: web_search, read_web_page
roles: all
---

Look in this order: the user's files, the Knowledge base (`search_rag`), the connectors (MCP),
then the web. The web is for what none of them gives: a price, a property, a standard, a site
fact.

Before you search, ask whether the value is needed at all: only a value gemini or the case needs
now (an error or `plants_need` names it) is looked for. When a module asks for a detail the brief
never mentions (a sand concentration, a filter rating), prefer one labelled engineering assumption
with a one-line reason in the confirmation question, or name it as a gap, over a long search.

Search only for a value nothing gives yet. A value the user's files, the brief
or the case already state (a supply temperature the brief fixes) is never searched for, and the
project, the hackathon or the chat itself is never a query.

Writing a query (`web_search(query, limit)`; the search is English only):

- English only, whatever language the user or the site uses. A query in another language, or
  longer than 8 words, is refused.
- One value per query, 3 to 6 technical terms, never a sentence, a question or chat text: the
  quantity, the technology, its unit, and the region and the year when they matter.
  Good: `geothermal well sand production ppm`, then
  `hydrocyclone desander geothermal brine specification`;
  `absorption chiller COP single effect`,
  `geothermal doublet drilling cost Netherlands 2024`,
  `electricity grid CO2 intensity Netherlands 2024 gCO2/kWh`,
  `KNMI De Bilt mean annual air temperature 1991-2020`.
  Bad: `produced sand concentration geothermal well kg/m3 brine solids removal cyclone
  specification` (two values, eleven words: generic pages came back),
  `Nederland warmtenet ontwerptemperatuur aanvoer` (not English),
  `GEMINI agentic geothermal design hackathon site location` (the project, not a value),
  `district heating supply and return temperature 100 C 20 C chilled water return temperature`
  (a pile of terms for two values, one the brief gives).
- One value per query. For a price, name what is priced and its basis (`EUR/kW`, `per m`).
- Results are weak (no primary source, off topic): try 2 or 3 refined queries: other or narrower
  terms, the technology's exact name, or a primary source's name (`IEA`, `IRENA`, `EU JRC`,
  `TNO`, a manufacturer). Stop after three and ask the user, naming what you searched.
- A result (title, url, snippet, engine, date) is a lead, never a source: a snippet can be cut or
  wrong.
- Prefer primary sources: agencies (IEA, IRENA, EU JRC, national statistics), operators, standards
  bodies, manufacturers' datasheets, peer-reviewed papers. Avoid forums, ads and pages that give
  no source of their own.

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

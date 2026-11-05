"""Tools over the global Knowledge base only, for a team's sub-agents (IMP-025).

Only a team lead reads and writes the project's files; a sub-agent may read the Knowledge base
(user decision, 2026-11-05), so these tools read only names inside ``knowledge/`` (a bare name gets the prefix).
"""

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.files import read_rag
from geomind.tools.gemini.results import knowledge_matches
from geomind.tools.knowledge import PREFIX


@tool(effect="read", keeps_result=True)
def search_knowledge(context, query: str):
    """Search the global Knowledge base only; return ``{matches}``, best first.

    Skill `finding-sources`.
    """
    matches = knowledge_matches(context, query)
    if matches is None:
        raise ToolError(
            "search_knowledge: this run has no Knowledge base; report the value missing",
            code="not_allowed",
        )
    return {"matches": matches[:8]}


@tool(effect="read", keeps_result="run")
def read_knowledge(
    context,
    name: str,
    start: int = 0,
    length: int | None = None,
    outline: bool = False,
    section: str | None = None,
    whole: bool = False,
):
    """Read one document of the Knowledge base, ``knowledge/<name>`` or ``<name>``, as text.

    Every name is a Knowledge document: a bare ``handbook-design.md`` reads
    ``knowledge/handbook-design.md`` (QA-169, QA-182). A long document without ``section``
    gives its contents first; then read only the sections needed (``section="7.4; 8.1"``).

    Skill `finding-sources`.
    """
    name = str(name).strip()
    if not name.startswith(PREFIX):
        name = PREFIX + name.lstrip("/")
    return read_rag.function(
        context, name, start=start, length=length, outline=outline, section=section, whole=whole
    )

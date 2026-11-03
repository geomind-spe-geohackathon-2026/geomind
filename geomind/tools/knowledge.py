"""The knowledge base: shared documents searched for cited values (``search_knowledge``).

A workspace gives it through the optional ``knowledge_search``, ``knowledge_files`` and
``knowledge_file``; ``read_document`` reads a whole document as ``knowledge/<name>``. A
workspace without them, or with no document, answers ``knowledge_unavailable``.
"""

from geomind.errors import ToolError
from geomind.tools.base import tool

SHOWN_PASSAGES = 8
"""The most passages one search returns, best first."""
PREFIX = "knowledge/"
"""How ``read_document`` names a document of the knowledge base."""


def has_knowledge(workspace):
    """Tell whether a workspace has the optional knowledge methods."""
    names = ("knowledge_search", "knowledge_files", "knowledge_file")
    return all(callable(getattr(workspace, name, None)) for name in names)


def knowledge_workspace(context, tool_name):
    """Return the run's workspace with a knowledge base, or raise ``knowledge_unavailable``."""
    workspace = context.session.workspace
    if not has_knowledge(workspace) or not workspace.knowledge_files():
        raise ToolError(
            f"{tool_name}: this run has no knowledge base; work from the case, the project's "
            "files and the user",
            code="knowledge_unavailable",
        )
    return workspace


@tool(effect="read")
def search_knowledge(context, query: str):
    """Search the shared knowledge base for passages that state a value, with their citation.

    Returns ``passages`` best first, each ``{id, document, title, page, text, score}``. A value
    taken from a passage is cited with its document, title and page, and goes into the case only
    after the user confirms it, as any value no project file gives. Read a whole document with
    ``read_document`` as ``knowledge/<document>``.
    """
    workspace = knowledge_workspace(context, "search_knowledge")
    return {"passages": list(workspace.knowledge_search(query))[:SHOWN_PASSAGES]}


def knowledge_file(context, tool_name, name):
    """Return the bytes of ``knowledge/<name>``, or raise ``unknown_name`` with the documents."""
    workspace = knowledge_workspace(context, tool_name)
    document = name.removeprefix(PREFIX)
    content = workspace.knowledge_file(document)
    if content is not None:
        return content
    names = [f"{PREFIX}{item['name']}" for item in workspace.knowledge_files()]
    raise ToolError(
        f"{tool_name}: document = {name!r}; expected one of {', '.join(names)}",
        code="unknown_name",
        path="name",
    )

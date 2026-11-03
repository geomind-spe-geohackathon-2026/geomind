"""The knowledge base: shared documents searched for cited values.

A workspace gives it through the optional ``knowledge_search``, ``knowledge_files`` and
``knowledge_file``; ``search_rag`` searches it beside the project, and ``read_rag`` reads a whole
document as ``knowledge/<name>``. Reading one from a workspace without them, or with no document,
answers ``knowledge_unavailable``.
"""

from geomind.errors import ToolError

PREFIX = "knowledge/"
"""How ``read_rag`` names a document of the knowledge base."""


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

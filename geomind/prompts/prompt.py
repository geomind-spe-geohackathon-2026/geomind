"""System prompts: from a role file or inline text."""

from pathlib import Path

from geomind.errors import UnknownNameError
from geomind.utils.strings import did_you_mean

FOLDER = Path(__file__).parent
SHARED_TOOLS = ("read_stored", "search_memory", "read_memory", "search_knowledge")
STORED_RESULTS = (
    "## Stored results\n\n"
    "A long result is whole for one step, then only its `reference`, small values and an outline. "
    "Get the rest with `read_stored(reference, path)` (dotted keys and indexes) or the tool again."
)
MEMORY = (
    "## Memory\n\n"
    "`search_memory` gives what the team learned before, when the memory is on: `experience`, "
    "designs that passed on an alike case, each with its `similarity`, and `lessons`, the general "
    "lessons of your role and the facts the user gave; `read_memory` reads one entry by its id. "
    "A past design is a starting point only: simulate, check and optimise again, and try at "
    "least one option that differs from it. A lesson is method, never a value of this case."
)
KNOWLEDGE = (
    "## Knowledge\n\n"
    "`search_knowledge` searches the shared knowledge base, documents such as cost catalogues, "
    "standards and reports, and returns passages with their document, title and page; "
    "`read_document` reads a whole one as `knowledge/<document>`. A value from it is cited with "
    "its document and page, and a value that enters the case is confirmed by the user, as any "
    "value no project file gives. Never take a value from memory where knowledge or a file "
    "gives one."
)


def role_files():
    """Return the prompt file of each role by ``<team>/<name>``; ``skills/`` holds skills."""
    return {
        f"{path.parent.name}/{path.stem}": path
        for path in sorted(FOLDER.glob("*/*.md"))
        if path.parent.name != "skills"
    }


class Prompt:
    """The system prompt of an agent; ``Prompt("design/lead")`` loads ``design/lead.md``.

    A role has one file, ``geomind/prompts/<team>/<name>.md``, as its agent is
    ``geomind/agents/<team>/<name>.py``.
    """

    def __init__(self, role, appendix=None):
        """Load the role file; an unknown role raises with a close match.

        ``appendix`` returns text made when the prompt is rendered, such as a key tree read from
        gemini's schema, so the prompt follows gemini without a copy of it.
        """
        self.appendix = appendix
        roles = role_files()
        if role not in roles:
            raise UnknownNameError(
                f"Prompt: role = {role!r}; expected a role file{did_you_mean(role, roles)}"
            )
        self.content = roles[role].read_text().strip()

    @classmethod
    def text(cls, content):
        """Return a prompt holding inline text."""
        prompt = cls.__new__(cls)
        prompt.content = content.strip()
        prompt.appendix = None
        return prompt

    def render(self):
        """Return the text of the system message, with the appendix made now."""
        if self.appendix is None:
            return self.content
        return f"{self.content}\n\n{self.appendix()}"

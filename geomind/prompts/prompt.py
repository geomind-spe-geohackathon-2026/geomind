"""System prompts: from a role file or inline text."""

from pathlib import Path

from geomind.errors import UnknownNameError
from geomind.utils.strings import did_you_mean

FOLDER = Path(__file__).parent
SHARED_TOOLS = ("read_stored", "search_memory", "read_memory", "write_memory")
STORED_RESULTS = (
    "## Stored results\n\n"
    "A long result is whole for one step, then only its `reference`, small values and an outline. "
    "Get the rest with `read_stored(reference, path)` (dotted keys and indexes) or the tool again."
)
MEMORY = (
    "## Memory\n\n"
    "`search_memory` reads the shared memory when it is on: `knowledge` holds cited reference "
    "values, each with its source and `status` (`verified`, `secondary`, `placeholder`); "
    "`experience` holds designs that passed before, each with its `similarity` to this case; "
    "`read_memory` reads one entry by its id. "
    "A value from knowledge is used with its source and status, and a `placeholder` is named as "
    "one. A past design is a starting point only: simulate, check and optimise again, and try "
    "at least one option that differs from it. `write_memory` adds a cited value to knowledge; "
    "a value without its source is never written."
)


def role_files():
    """Return the prompt file of each role; ``skills/`` holds skills, not roles."""
    paths = FOLDER.glob("*/*.md")
    return {path.stem: path for path in paths if path.parent.name != "skills"}


class Prompt:
    """The system prompt of an agent; ``Prompt("analyst")`` loads ``<folder>/analyst.md``.

    A role has one file, in the folder of its area, as its agent has.
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

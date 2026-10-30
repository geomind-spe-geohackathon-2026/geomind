"""System prompts: from a role file or inline text."""

from pathlib import Path

from geomind.errors import UnknownNameError
from geomind.utils.strings import did_you_mean

FOLDER = Path(__file__).parent


def role_files():
    """Return the prompt file of each role; ``skills/`` holds skills, not roles."""
    paths = FOLDER.glob("*/*.md")
    return {path.stem: path for path in paths if path.parent.name != "skills"}


class Prompt:
    """The system prompt of an agent; ``Prompt("analyst")`` loads ``<folder>/analyst.md``.

    A role has one file, in the folder of its area, as its agent has.
    """

    def __init__(self, role):
        """Load the role file; an unknown role raises with a close match."""
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
        return prompt

    def render(self):
        """Return the text of the system message."""
        return self.content

"""System prompts: from a role file or inline text."""

from pathlib import Path

from swarmax.errors import UnknownNameError
from swarmax.utils.strings import did_you_mean

FOLDER = Path(__file__).parent


class Prompt:
    """The system prompt of an agent; ``Prompt("assistant")`` loads ``assistant.md``."""

    def __init__(self, role):
        """Load the role file; an unknown role raises with a close match."""
        path = FOLDER / f"{role}.md"
        if not path.is_file():
            roles = [item.stem for item in FOLDER.glob("*.md")]
            raise UnknownNameError(
                f"Prompt: role = {role!r}; expected a role file{did_you_mean(role, roles)}"
            )
        self.content = path.read_text().strip()

    @classmethod
    def text(cls, content):
        """Return a prompt holding inline text."""
        prompt = cls.__new__(cls)
        prompt.content = content.strip()
        return prompt

    def render(self):
        """Return the text of the system message."""
        return self.content

"""Instructions a model loads when it needs them, from ``prompts/skills/*.md``.

The first paragraph of a skill file is its one line in the system prompt.
"""

from geomind.errors import UnknownNameError
from geomind.prompts.prompt import FOLDER
from geomind.utils.strings import did_you_mean, first_paragraph

SKILLS = FOLDER / "skills"


def skill_names():
    """Return the names of the skills, sorted."""
    return sorted(path.stem for path in SKILLS.glob("*.md"))


def load_skill(name):
    """Return the text of one skill; an unknown name raises with the close match."""
    path = SKILLS / f"{name}.md"
    if name not in skill_names():
        raise UnknownNameError(
            f"read_skill: name = {name!r}; expected a skill{did_you_mean(name, skill_names())}"
        )
    return path.read_text().strip()


def skill_listing():
    """Return what the system prompt says about skills: names with one line each."""
    lines = [f"- {name}: {first_paragraph(load_skill(name))}" for name in skill_names()]
    return "\n".join(["Skills you can read with read_skill:", *lines])

"""What every skeleton agent must look like."""

import inspect
import re

from geomind.prompts.prompt import role_files

HEADINGS = ["Role", "Inputs", "Tools", "Rules", "Output", "Examples"]
SECTIONS = ["Agents", "Prompt", "Tools", "Output", "Model"]


def headings(text):
    """Return the second-level headings of a prompt, in order."""
    return re.findall(r"^## (.+)$", text, flags=re.MULTILINE)


def check_skeleton(agent_class, role):
    """Check one skeleton: it constructs, its prompt has the headings, its sections are in order."""
    agent = agent_class()
    assert agent.prompt is not None
    text = role_files()[role].read_text()
    assert headings(text) == HEADINGS
    assert all(
        len(section.strip().splitlines()) == 1
        for section in re.split("^## .*$", text, flags=re.M)[1:]
    )
    source = inspect.getsource(agent_class.__init__)
    found = re.findall(r"^\s+# (\w+)$", source, flags=re.MULTILINE)
    assert found == [name for name in SECTIONS if name in found]
    assert "Prompt" in found and "Model" in found
    assert "forward" not in vars(agent_class)
    assert "NOTE: the structure is fixed now" in " ".join(agent_class.__doc__.split())

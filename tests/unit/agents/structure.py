"""What every skeleton agent must look like."""

import inspect
import re

from geomind.prompts.prompt import SHARED_TOOLS, role_files

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


def named_tools(text):
    """Return the tools a prompt names in its ``## Tools`` section."""
    section = text.split("## Tools")[1].split("## Rules")[0]
    return re.findall(r"^- `(\w+)`", section, flags=re.MULTILINE)


def check_complete(agent_class, role, tools):
    """Check a filled agent: its tools in order, every heading filled, only its tools named."""
    agent = agent_class()
    text = role_files()[role].read_text()
    assert list(agent.tools()) == tools
    assert headings(text) == HEADINGS
    sections = re.split(r"^## .*$", text, flags=re.MULTILINE)[1:]
    assert all(section.strip() for section in sections)
    assert len(text.splitlines()) > 25
    assert sorted(named_tools(text)) == sorted(set(tools) - set(SHARED_TOOLS))
    assert "NOTE: the structure is fixed now" not in " ".join(agent_class.__doc__.split())

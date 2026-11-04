"""The agent that keeps the general lessons of a run for each role."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


def agent_roles():
    """Return the snake names a lesson may be for: every agent's, and ``all``."""
    import inspect

    import geomind.agents as agents

    classes = [item for item in vars(agents).values() if inspect.isclass(item)]
    names = {item().name for item in classes if issubclass(item, Agent) and item is not Agent}
    return sorted(names | {"all"})


def roles_text():
    """Return the roles a lesson may be for, from the agents themselves."""
    return "## Roles\n\n" + ", ".join(f"`{role}`" for role in agent_roles())


class Curator(Agent):
    """Write the general lessons of a run for each role, and the user's facts, into experience.

    NOTE: it writes method in words, with its origin, never a project's numbers as a rule
    (``write_lesson`` refuses a digit in a lesson). An approved design is kept by code alone,
    after the reviewer passed it; the curator never writes one.
    """

    def __init__(self):
        """Declare the prompt, the memory tools and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("support/curator", appendix=roles_text)

        # Tools
        self.read_case = tools.gemini.read_case
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.write_lesson = tools.write_lesson
        self.finish = tools.finish

        # Model
        self.model = Model(setting="curator_model", temperature=0)

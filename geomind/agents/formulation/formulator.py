"""The agent that sets the case: demand, site, requirements and time, from the files."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt
from geomind.tools.gemini.skeleton import case_tree


class Formulator(Agent):
    """Set the case of a design from the project's files, with assumptions for what they lack.

    NOTE: the formulator owns the case and designs nothing; the designer reads the case and never
    sets it. The design and compare loops run the formulator once before any design, and again only
    when a round reports that the case must change.
    """

    def __init__(self):
        """Declare the prompt, the tools over files and the case, and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("formulator", appendix=case_tree)

        # Tools
        self.list_files = tools.list_files
        self.read_document = tools.read_document
        self.search_documents = tools.search_documents
        self.read_case = tools.gemini.read_case
        self.set_case = tools.gemini.set_case
        self.save_profile = tools.gemini.save_profile
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.write_memory = tools.write_memory
        self.update_state = tools.update_state
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="formulator_model", temperature=0)

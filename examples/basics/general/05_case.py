"""Run a project's case through gemini with a scripted model: set the case, simulate its plant."""

from pathlib import Path

import geomind as gd
from examples.support import provider
from geomind.types import Completion, ToolCall

PROJECTS = Path(__file__).resolve().parents[3] / "evals" / "projects"
SCRIPT = [
    Completion(tool_calls=(ToolCall(id="c1", name="set_case", input={"source": "project"}),)),
    Completion(tool_calls=(ToolCall(id="c2", name="simulate", input={}),)),
    Completion(tool_calls=(ToolCall(id="c3", name="finish", input={"answer": "Simulated."}),)),
]


class Simulator(gd.Agent):
    """Sets the project's case and simulates the project's plant on it."""

    def __init__(self):
        """Declare the prompt, the tools and the model."""
        super().__init__()

        # Prompt
        self.prompt = gd.Prompt.text("Set the project's case, simulate its plant, then finish.")

        # Tools
        self.set_case = gd.tools.gemini.set_case
        self.simulate = gd.tools.gemini.simulate
        self.finish = gd.tools.finish

        # Model
        self.model = gd.Model(temperature=0)


def main():
    """Run the agent on the hackathon project and print what gemini found."""
    store = gd.stores.MemoryRunStore()
    run = gd.Run(
        message="Simulate the project's plant.",
        project="hackathon_plant",
        workspace=gd.stores.FileWorkspace(PROJECTS),
        llm=provider(SCRIPT),
        store=store,
        agent=Simulator(),
        permissions=gd.Permissions(mode="auto"),
    )
    run.start()
    events = store.load_events(run.id)
    summary = next(e.output for e in events if e.type == "tool.result" and e.tool == "simulate")
    print(f"steps: {summary['summary']['steps']}")
    print(f"violated constraints: {len(summary['summary']['violated'])}")


if __name__ == "__main__":
    main()

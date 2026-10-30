"""A custom agent with its own tool, driven by the engine."""

import asyncio

import swarmax as sx
from examples.support import provider
from swarmax.core.types import Completion, ToolCall


@sx.tool(effect="compute")
def add(left: int, right: int):
    """Add two numbers."""
    return left + right


class Adder(sx.Agent):
    """Adds numbers with its tool."""

    def __init__(self):
        """Declare the prompt, the tool and the model."""
        super().__init__()

        # Prompt
        self.prompt = sx.Prompt.text("Use the tool, then answer with the number.")

        # Tools
        self.add = add
        self.finish = sx.tools.finish

        # Model
        self.model = sx.Model(temperature=0)


SCRIPT = [
    Completion(tool_calls=(ToolCall(id="c1", name="add", input={"left": 2, "right": 40}),)),
    Completion(tool_calls=(ToolCall(id="c2", name="finish", input={"answer": "42"}),)),
]


async def main():
    """Print the agent, then run it."""
    print(Adder.help())
    engine = sx.Engine(llm=provider(SCRIPT))
    context = sx.Context(messages=[sx.Message(role="user", content="What is 2 + 40?")])
    result = await sx.loops.ToolLoop(Adder()).run(engine, context)
    print(result.answer)


if __name__ == "__main__":
    asyncio.run(main())

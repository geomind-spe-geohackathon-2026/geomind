"""A hook pauses before a tool, and the answer decides."""

import asyncio

import swarmax as sx
from examples.support import provider
from swarmax.types import Completion, ToolCall


@sx.tool(effect="external")
def send_report(address: str):
    """Send the report to an address."""
    return f"sent to {address}"


class Sender(sx.Agent):
    """Sends reports."""

    def __init__(self):
        """Declare the tool."""
        super().__init__()

        # Tools
        self.send_report = send_report


SCRIPT = [
    Completion(tool_calls=(ToolCall(id="c1", name="send_report", input={"address": "a@b"}),)),
    Completion(text="The report is sent."),
]


async def main():
    """Pause on the tool, then approve it."""
    hooks = [sx.hooks.RequireApproval(["send_report"])]
    engine = sx.Engine(hooks=hooks, llm=provider(SCRIPT))
    context = sx.Context(messages=[sx.Message(role="user", content="Send the report")])
    paused = await engine.run(Sender(), context)
    print(paused.status, paused.request.message)
    checkpoint = engine.store.load_checkpoint(context.run_id)
    result = await engine.resume(checkpoint, paused.request.id, {"approved": True})
    print(result.answer)


if __name__ == "__main__":
    asyncio.run(main())

"""A hook pauses before a tool, and the answer decides."""

import asyncio

import geomind as gd
from examples.support import provider
from geomind.types import Completion, ToolCall


@gd.tool(effect="external")
def send_report(address: str):
    """Send the report to an address."""
    return f"sent to {address}"


class Sender(gd.Agent):
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
    hooks = [gd.hooks.RequireApproval(["send_report"])]
    engine = gd.Engine(hooks=hooks, llm=provider(SCRIPT))
    context = gd.Context(messages=[gd.Message(role="user", content="Send the report")])
    paused = await engine.run(Sender(), context)
    print(paused.status, paused.request.message)
    result = await engine.resume(context.run_id, paused.request.id, {"approved": True})
    print(result.answer)


if __name__ == "__main__":
    asyncio.run(main())

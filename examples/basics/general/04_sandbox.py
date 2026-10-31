"""The model writes and runs a small calculation in the local sandbox."""

import geomind as gd
from examples.support import provider
from geomind.types import Completion, ToolCall

CODE = "print(sum(range(1, 101)))"
ROUTE = '{"kind": "loop", "loop": "tool", "agent": "code_assistant"}'
SCRIPT = [
    Completion(text=ROUTE),
    Completion(tool_calls=(ToolCall(id="c1", name="run_python", input={"code": CODE}),)),
    Completion(text="The sum is 5050."),
]


def main():
    """Run with the sandbox and approve the code by rule."""
    store = gd.stores.MemoryRunStore()
    run = gd.Run(
        message="Add the numbers from 1 to 100 with Python",
        llm=provider(SCRIPT),
        store=store,
        sandbox=gd.sandbox.LocalSandbox(),
        permissions=gd.Permissions(allow=("run_python",)),
    )
    result = run.start()
    events = store.load_events(run.id)
    output = next(e.output for e in events if e.type == "tool.result" and e.tool == "run_python")
    print(output["stdout"].strip())
    print(result.answer)


if __name__ == "__main__":
    main()

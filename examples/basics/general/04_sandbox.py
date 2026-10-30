"""The model writes and runs a small calculation in the local sandbox."""

import swarmax as sx
from examples.support import provider
from swarmax.types import Completion, ToolCall

CODE = "print(sum(range(1, 101)))"
SCRIPT = [
    Completion(tool_calls=(ToolCall(id="c1", name="run_python", input={"code": CODE}),)),
    Completion(text="The sum is 5050."),
]


def main():
    """Run with the sandbox and approve the code by rule."""
    store = sx.stores.MemoryRunStore()
    run = sx.Run(
        message="Add the numbers from 1 to 100 with Python",
        llm=provider(SCRIPT),
        store=store,
        sandbox=sx.sandbox.LocalSandbox(),
        permissions=sx.Permissions(allow=("run_python",)),
    )
    result = run.start()
    output = next(e.output for e in store.load_events(run.id) if e.type == "tool.result")
    print(output["stdout"].strip())
    print(result.answer)


if __name__ == "__main__":
    main()

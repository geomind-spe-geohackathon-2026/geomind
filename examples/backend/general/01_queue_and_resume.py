"""The backend flow: start in one function, resume in another, events forwarded as SSE lines.

Each function builds everything anew, as two queue jobs in two processes would. Only the store
connects them.
"""

import json
import sys
import tempfile

import geomind as gd
from examples.support import provider
from geomind.types import Completion, ToolCall

SCRIPT = [
    Completion(tool_calls=(ToolCall(id="c1", name="run_python", input={"code": "print(1)"}),)),
    Completion(text="Done."),
]


class Publisher(gd.callbacks.Callback):
    """Forward public events as server-sent event lines."""

    def on_event(self, engine, event):
        """Write one event."""
        if event.is_public:
            data = json.dumps(event.data())
            sys.stdout.write(f"event: {event.type}\ndata: {data}\nid: {event.sequence}\n\n")


def permissions():
    """Return the permissions of both jobs."""
    return gd.Permissions(mode="ask")


def start_job(root, sandbox_root):
    """Start a run from a chat message; return its id and pending request id."""
    run = gd.Run(
        message="Run a small script",
        llm=provider(SCRIPT),
        store=gd.stores.FileRunStore(root),
        sandbox=gd.sandbox.LocalSandbox(sandbox_root),
        permissions=permissions(),
        callbacks=[Publisher()],
    )
    result = run.start()
    return run.id, result.request.id


def answer_job(root, sandbox_root, run_id, request_id):
    """Answer the request in a fresh run."""
    run = gd.Run.load(
        run_id,
        llm=provider(SCRIPT[1:]),
        store=gd.stores.FileRunStore(root),
        sandbox=gd.sandbox.LocalSandbox(sandbox_root),
        permissions=permissions(),
        callbacks=[Publisher()],
    )
    return run.resume(request_id, {"approved": True})


def main():
    """Run both jobs and print the log's status."""
    with tempfile.TemporaryDirectory() as folder:
        run_id, request_id = start_job(f"{folder}/runs", f"{folder}/sandbox")
        result = answer_job(f"{folder}/runs", f"{folder}/sandbox", run_id, request_id)
        log = gd.runlog(gd.stores.FileRunStore(f"{folder}/runs").load_events(run_id))
    print(result.answer, log["run"]["status"], len(log["steps"]))


if __name__ == "__main__":
    main()

"""Tools that act inside the run's sandbox."""

import hashlib

from geomind import runtime
from geomind.errors import SandboxError
from geomind.tools.base import tool
from geomind.utils.time import parse_duration

SCRIPT = "main.py"
CUT_SHARE = 3


async def _in_sandbox(context, action):
    """Run ``action(sandbox)``; a lost sandbox is dropped, so the next tool gets a new one."""
    session = context.session
    sandbox = await session.sandbox()
    try:
        return await action(sandbox)
    except SandboxError:
        await session.lose_sandbox()
        raise


async def _cut(context, text):
    """Return text within the size limit, with the full text saved as an artifact.

    Each text gets a share of the limit, so a result holding two of them, with their keys, still
    fits and dispatch does not replace the whole result by a reference.
    """
    limit = runtime.get("tool_result_limit") // CUT_SHARE
    if len(text) <= limit:
        return text
    key = f"output-{hashlib.sha256(text.encode()).hexdigest()[:16]}"
    await context.session.save_artifact(key, text)
    return f"{text[:limit]}\n[cut; the full text is artifact {key}]"


@tool(effect="execute", idempotent=False)
async def run_python(context, code: str):
    """Run Python code in the sandbox and return its exit code and output."""

    async def action(sandbox):
        await sandbox.write(SCRIPT, code.encode())
        timeout = parse_duration(runtime.get("sandbox_timeout"))
        return await sandbox.execute(["python", SCRIPT], timeout=timeout)

    result = await _in_sandbox(context, action)
    return {
        "exit_code": result.exit_code,
        "stdout": await _cut(context, result.stdout),
        "stderr": await _cut(context, result.stderr),
        "duration": result.duration,
    }


@tool(effect="write")
async def write_file(context, path: str, text: str):
    """Write a text file in the sandbox."""

    async def action(sandbox):
        await sandbox.write(path, text.encode())

    await _in_sandbox(context, action)
    return {"written": path}


@tool(effect="execute")
async def read_file(context, path: str):
    """Read a text file from the sandbox."""

    async def action(sandbox):
        return await sandbox.read(path)

    return await _cut(context, (await _in_sandbox(context, action)).decode(errors="replace"))

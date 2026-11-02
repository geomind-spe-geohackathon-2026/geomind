"""The script that runs inside the sandbox: import a module file, check its classes, print JSON.

The harness never imports this file; it copies its text into the sandbox next to the agent's code.
The file's own output goes to standard error, so standard output holds only the report.
"""

import contextlib
import importlib.util
import json
import sys
from pathlib import Path


def load(path):
    """Import the file at ``path`` and return the module."""
    spec = importlib.util.spec_from_file_location("agent_module", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def module_classes(module):
    """Return the ``gm.modules.Module`` classes the file defines, not those it imports."""
    import gemini as gm

    return [
        item
        for item in vars(module).values()
        if isinstance(item, type)
        and issubclass(item, gm.modules.Module)
        and item.__module__ == module.__name__
        and not item.__dict__.get("abstract", False)
    ]


def run(path, example_path):
    """Return ``{reports}`` of ``gm.modules.check`` per class, or ``{error}`` if the file fails."""
    import gemini as gm

    example = json.loads(Path(example_path).read_text()) if Path(example_path).exists() else None
    try:
        with contextlib.redirect_stdout(sys.stderr):
            classes = module_classes(load(path))
            return {"reports": [gm.modules.check(item, example) for item in classes]}
    except Exception as error:
        return {"error": {"type": type(error).__name__, "message": str(error)}}


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1], sys.argv[2])))

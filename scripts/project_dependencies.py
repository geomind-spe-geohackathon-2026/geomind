"""Print the runtime dependencies of ``pyproject.toml``, gemini left out, for ``make install``."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEMINI = "gemini-geothermal-suite-open"


def main():
    """Print one requirement per line; gemini comes from ``requirements/gemini.txt``."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    for requirement in project["dependencies"]:
        if not requirement.startswith(GEMINI):
            print(requirement)


if __name__ == "__main__":
    main()

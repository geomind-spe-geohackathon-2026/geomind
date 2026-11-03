"""No Anthropic model id in the package, the evals, the examples or the docs."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = ("geomind", "evals", "examples", ".claude/docs", "docs")
SUFFIXES = {".py", ".md", ".json", ".txt", ".toml", ".yaml", ".yml"}
PATTERN = re.compile(r"anthropic/|claude-[a-z0-9]|\b(?:sonnet|haiku|opus)[ -]?\d", re.IGNORECASE)
ALLOWED = {("geomind/live.py", "FORBIDDEN_PREFIX")}
RECORDED = ("evals/recordings", "evals/runs", ".jsonl")


def sources():
    """Return the files to scan; recorded runs keep the model they ran on."""
    for folder in FOLDERS:
        for path in (ROOT / folder).rglob("*"):
            relative = path.relative_to(ROOT).as_posix()
            if path.suffix in SUFFIXES and not any(part in relative for part in RECORDED):
                yield path


def is_allowed(path, line):
    """Tell whether a line is an attribution line or an allowed constant."""
    relative = path.relative_to(ROOT).as_posix()
    return "Co-Authored-By" in line or any(
        relative == file and name in line for file, name in ALLOWED
    )


def test_no_anthropic_model_id_is_named():
    """Only recorded runs, the changelog, attribution lines and one named constant may name one."""
    found = [
        f"{path.relative_to(ROOT)}:{number}: {line.strip()[:80]}"
        for path in sources()
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1)
        if PATTERN.search(line) and not is_allowed(path, line)
    ]
    assert not found, "\n".join(found)

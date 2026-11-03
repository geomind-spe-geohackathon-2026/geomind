"""Every relative link in the agent map and the docs resolves."""

import re

import pytest

from tests.fixtures import ROOT

DOCUMENTS = [
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    *sorted((ROOT / "docs").glob("*.md")),
    *sorted((ROOT / ".claude/docs").glob("*.md")),
]
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#+ (.+)$", re.MULTILINE)
SHARED_DOCS = ROOT.parent / "docs"


def anchors(path):
    """Return the heading anchors of one Markdown file."""
    headings = HEADING.findall(path.read_text())
    return {re.sub(r"[^\w\- ]", "", text).lower().replace(" ", "-") for text in headings}


def is_checkable(target):
    """Tell whether a link target can be checked here; ``../docs`` is a sibling folder."""
    return target.is_relative_to(ROOT) or SHARED_DOCS.exists()


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: path.name)
def test_links_resolve(document):
    """Each relative link names an existing file and, where given, an existing heading."""
    broken = []
    for link in LINK.findall(document.read_text()):
        if link.startswith("http"):
            continue
        name, _, anchor = link.partition("#")
        target = (document.parent / name).resolve() if name else document
        if not is_checkable(target):
            continue
        if not target.exists() or (anchor and anchor not in anchors(target)):
            broken.append(link)
    assert broken == []

"""geomind uses gemini's public API only, none of its removed names, and no hackathon figure."""

import ast
import re
import tomllib

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from tests.fixtures import ROOT
from tests.unit.test_code_quality import tracked_files

PRIVATE_ATTRIBUTES = {"_set_inputs", "frame"}
REMOVED_NAMES = re.compile(
    "|".join(
        (
            r"gm\.profiles",
            r"gm\.kpi",
            r"gm\.checks",
            r"gm\.economics",
            r"gm\.units\.parse",
            r"from_template",
            r"spec_schema",
            r"plants\.example",
            r"Plant\.validate",
            r"from_legacy",
            r"\bBrief\b",
            r"set_brief",
            r"hackathon_2027",
            r"profile/<",
            r"gm\.data\b",
            r"gm\.case\.roles",
            r"gm\.plants\.validate",
            r"missing_parameters",
            r"\bConstraint\b",
            r"\bChoices\b",
            r"gm\.(?:\w+\.)*Assumptions\b",
            r"inputs/examples",
            r"run_all",
            r"gm\.physics\.control",
            r"\bbackup=",
            r"\bvariables=",
        )
    )
)
HACKATHON = re.compile(
    r"hackathon|2027|30 K/km|2500 m\b|37\.58|48\.48",
    re.IGNORECASE,
)
DOC_FILES = ("AGENTS.md",)


def geomind_files():
    """Return every tracked file of the package, code, prompts, skills and schemas."""
    return [path for path in tracked_files() if path.startswith("geomind/")]


def doc_files():
    """Return the docs read by a new session."""
    return [
        path for path in tracked_files() if path.startswith(".claude/docs/") or path in DOC_FILES
    ]


def text_of(path):
    """Return the text of a file, empty for a binary one."""
    try:
        return (ROOT / path).read_text()
    except UnicodeDecodeError:
        return ""


def lines_matching(paths, pattern):
    """Return ``path:line: text`` for every line of the files that matches."""
    return [
        f"{path}:{number}: {line.strip()}"
        for path in paths
        for number, line in enumerate(text_of(path).splitlines(), 1)
        if pattern.search(line)
    ]


def private_module_parts(name):
    """Return whether a dotted name is gemini's and has a private part."""
    parts = name.split(".")
    return parts[0] == "gemini" and any(is_private(part) for part in parts)


def private_gemini_uses(tree):
    """Yield ``(line, name)`` for each private gemini import of one parsed file."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
        else:
            continue
        for name in names:
            if private_module_parts(name):
                yield node.lineno, name


def is_private(name):
    """Return whether a name is private: one underscore first, not a dunder."""
    return name.startswith("_") and not name.startswith("__")


def attribute_chain(node):
    """Return the dotted names of an attribute expression, or an empty list."""
    names = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        names.append(node.id)
    return names[::-1]


def private_attribute_uses(tree):
    """Yield ``(line, name)`` for private gemini attributes and hand-set frames."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        chain = attribute_chain(node)
        if chain[:1] == ["gm"] and any(is_private(part) for part in chain[1:]):
            yield node.lineno, ".".join(chain)
        if node.attr == "_set_inputs":
            yield node.lineno, "._set_inputs"
        if node.attr == "frame" and isinstance(node.ctx, ast.Store):
            yield node.lineno, ".frame ="


def private_names_in(source):
    """Return every private gemini name used by one source text."""
    tree = ast.parse(source)
    return sorted(set(private_gemini_uses(tree))) + sorted(set(private_attribute_uses(tree)))


def test_geomind_uses_no_private_gemini_name():
    """No ``gm._x``, no ``gemini.*._x`` import, no ``._set_inputs`` and no hand-set ``.frame``."""
    found = [
        f"{path}:{line}: {name}"
        for path in tracked_files()
        if path.startswith("geomind/") and path.endswith(".py")
        for line, name in private_names_in(text_of(path))
    ]
    assert not found, "private gemini names:\n" + "\n".join(found)


@pytest.mark.parametrize(
    "source",
    [
        "import gemini as gm\ngm._utils.x()",
        "from gemini.plants._utils import x",
        "import gemini.plants._utils",
        "plant._set_inputs(1)",
        "results.frame = other",
    ],
)
def test_the_private_name_check_sees_a_violation(source):
    """The check fails on each planted private name."""
    assert private_names_in(source)


def test_the_private_name_check_accepts_the_public_api():
    """Public names, and a ``frame`` that is only read, are not violations."""
    assert not private_names_in("import gemini as gm\nx = gm.units.Quantity(1, 'm')\ny = z.frame")


def test_no_removed_gemini_name_in_the_package_or_the_docs():
    """The names gemini removed are in no code, prompt, skill or doc."""
    found = lines_matching(geomind_files() + doc_files(), REMOVED_NAMES)
    assert not found, "removed names:\n" + "\n".join(found)


def test_the_removed_name_check_sees_a_violation():
    """The pattern matches each removed name."""
    names = (
        "gm.profiles.get",
        "Brief(",
        "set_brief",
        "profile/<name>",
        "Plant.validate",
        "gm.data.from_values",
        "gm.case.roles()",
        "gm.plants.validate(x)",
        "plant.missing_parameters()",
        "Constraint(",
        "Choices(",
        "gm.Assumptions",
        "inputs/examples",
        "gm.evaluate.run_all",
        "gm.physics.control",
        "size(plant, backup=",
        "minimize(variables=",
    )
    for name in names:
        assert REMOVED_NAMES.search(name), name


def test_no_hackathon_name_or_figure_in_the_package():
    """The package is general: no hackathon, no 2027 demand year, no challenge figure."""
    found = lines_matching(geomind_files(), HACKATHON)
    assert not found, "hackathon names:\n" + "\n".join(found)


def test_the_hackathon_check_sees_a_violation():
    """The pattern matches the name and each figure."""
    for text in ("Hackathon", "the 2027 year", "30 K/km", "2500 m", "37.58", "48.48"):
        assert HACKATHON.search(text), text


def test_the_installed_gemini_is_in_the_supported_range():
    """``pyproject.toml`` pins gemini to 0.5 and the installed version satisfies the pin."""
    import gemini as gm

    dependencies = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    pins = [Requirement(item) for item in dependencies if "gemini" in item]
    assert [pin.specifier for pin in pins] == [SpecifierSet(">=0.5,<0.6")]
    assert Version(gm.__version__) in pins[0].specifier, f"unsupported gemini {gm.__version__}"

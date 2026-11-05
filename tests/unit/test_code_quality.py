"""The code-quality bar of ``.claude/docs/conventions.md`` cannot silently drop.

McCabe complexity is checked by flake8 (``max-complexity = 10`` in ``pyproject.toml``).
"""

import ast
import io
import re
import subprocess
import tokenize

import pytest

from tests.fixtures import ROOT

PYTHON_FOLDERS = ("geomind", "examples", "tests", "scripts", "evals")
SECTION_HEADERS = {"# Agents", "# Prompt", "# Tools", "# Output", "# Model"}
TOOL_DIRECTIVE = re.compile(
    r"# (noqa: [A-Z]+\d+(, [A-Z]+\d+)*|type: ignore\[[\w-]+\]|pragma: no cover)"
)
NESTING = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith, ast.Match)
MAX_NESTING = 3
MAX_LINES = 40
LONG_FUNCTIONS = {}
EARLY_EXITS = (ast.Return, ast.Raise, ast.Continue, ast.Break)
BUILTIN_ERRORS = {"ValueError", "TypeError", "KeyError", "RuntimeError"}
VALIDATORS = {"model_validator", "field_validator"}
FRAMEWORK = re.compile(
    "|".join(
        (
            "py" + "tor" + "ch",
            "\\b" + "tor" + "ch\\b",
            "lang" + "chain",
            "lang" + "graph",
            "crew" + "ai",
            "auto" + "gen",
            "llama" + "index",
            "pydantic[- ]" + "ai",
            "agents? " + "sdk",
        )
    )
)
FORMER_NAME = re.compile("swa" + "rm|\\bs" + "x\\.")


def tracked_files():
    """Return the repository's tracked and new, not ignored, files."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return sorted(path for path in set(listed) if (ROOT / path).is_file())


def python_files():
    """Return every Python file in the checked folders."""
    return [
        path for path in tracked_files() if path.endswith(".py") and path.startswith(PYTHON_FOLDERS)
    ]


def functions(path):
    """Yield every function definition of one file."""
    for node in ast.walk(ast.parse((ROOT / path).read_text())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def body_lines(function):
    """Return the number of lines of a function body, excluding its docstring."""
    body = function.body
    if ast.get_docstring(function) is not None:
        body = body[1:]
    return body[-1].end_lineno - body[0].lineno + 1 if body else 0


def nesting(node, depth=0):
    """Return the deepest block nesting inside a node; an ``elif`` chain counts once."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        is_elif = isinstance(node, ast.If) and node.orelse == [child] and isinstance(child, ast.If)
        nested = isinstance(child, NESTING) and not is_elif
        deepest = max(deepest, nesting(child, depth + 1 if nested else depth))
    return deepest


PYTHON_FILES = python_files()
PACKAGE_FILES = [
    path
    for path in PYTHON_FILES
    if path.startswith("geomind/") and not path.startswith("geomind/utils/")
]


@pytest.mark.parametrize("path", PYTHON_FILES)
def test_only_section_headers_and_tool_directives_are_comments(path):
    """Explanations live in docstrings, never in comments inside code."""
    found = []
    source = io.StringIO((ROOT / path).read_text())
    for token in tokenize.generate_tokens(source.readline):
        text = token.string.strip()
        is_allowed = text in SECTION_HEADERS or TOOL_DIRECTIVE.fullmatch(text)
        if token.type == tokenize.COMMENT and not is_allowed:
            found.append(f"{path}:{token.start[0]}: {text}")
    assert found == []


@pytest.mark.parametrize("path", PYTHON_FILES)
def test_functions_nest_at_most_three_blocks(path):
    """Guard clauses keep every function at most three blocks deep."""
    deep = [
        f"{path}:{function.lineno} {function.name} ({nesting(function)})"
        for function in functions(path)
        if nesting(function) > MAX_NESTING
    ]
    assert deep == []


@pytest.mark.parametrize("path", PYTHON_FILES)
def test_functions_are_short_or_documented_exceptions(path):
    """Functions stay within about 40 lines; each longer one is listed with its reason."""
    long = {
        f"{path}::{function.name}"
        for function in functions(path)
        if body_lines(function) > MAX_LINES
    }
    assert long == {name for name in LONG_FUNCTIONS if name.startswith(f"{path}::")}


def test_long_function_exceptions_exist():
    """Every listed long-function exception names an existing function."""
    paths = {name.partition("::")[0] for name in LONG_FUNCTIONS}
    names = {f"{path}::{function.name}" for path in paths for function in functions(path)}
    assert set(LONG_FUNCTIONS) <= names


@pytest.mark.parametrize("path", PYTHON_FILES)
def test_no_else_after_an_early_exit(path):
    """A block that ends in ``return``, ``raise``, ``continue`` or ``break`` has no ``else``."""
    found = [
        f"{path}:{node.lineno}"
        for node in ast.walk(ast.parse((ROOT / path).read_text()))
        if isinstance(node, ast.If) and node.orelse and isinstance(node.body[-1], EARLY_EXITS)
    ]
    assert found == []


def raised_name(node):
    """Return the class name a ``raise`` statement raises, or None."""
    exception = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
    return exception.id if isinstance(exception, ast.Name) else None


def is_validator(function):
    """Tell whether a function is a validator, which must raise ``ValueError``."""
    return any(
        isinstance(decorator, ast.Call) and getattr(decorator.func, "id", None) in VALIDATORS
        for decorator in function.decorator_list
    )


@pytest.mark.parametrize("path", PACKAGE_FILES)
def test_package_code_raises_geomind_errors(path):
    """Deliberate errors use ``gd.errors``; ``geomind.utils`` and validators are the exceptions."""
    found = [
        f"{path}:{node.lineno} {raised_name(node)}"
        for function in functions(path)
        if not is_validator(function)
        for node in ast.walk(function)
        if isinstance(node, ast.Raise) and node.exc and raised_name(node) in BUILTIN_ERRORS
    ]
    assert found == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def f():\n    if a:\n        for b in c:\n            pass\n", 2),
        ("def f():\n    if a:\n        pass\n    elif b:\n        pass\n", 1),
    ],
)
def test_nesting_counts_blocks_but_not_elif_chains(source, expected):
    """The nesting measure ignores ``elif`` chains."""
    assert nesting(ast.parse(source).body[0]) == expected


def lines_matching(pattern, skipped=(), skipped_folders=()):
    """Return ``path:line`` of every match in lower-cased tracked text.

    Only files with a match are split into lines, and the search runs on lower-cased text instead
    of ignoring case, because that keeps this within the budget of one test under parallel load.
    """
    found = []
    for path in tracked_files():
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if path in skipped or path.startswith(skipped_folders) or not pattern.search(text.lower()):
            continue
        found.extend(
            f"{path}:{number}"
            for number, line in enumerate(text.splitlines(), 1)
            if pattern.search(line.lower())
        )
    return found


ARCHIVE = (".claude/archive/",)
"""Historical records, never edited: what they named then stays as it was written."""


def test_no_framework_names_in_tracked_text_files():
    """Concepts are described directly, without naming another framework.

    ``.claude/archive/`` is left out: it records past sessions as they were and is never edited.
    """
    assert lines_matching(FRAMEWORK, skipped_folders=ARCHIVE) == []


def test_no_former_name_in_tracked_text_files():
    """The former package name and alias are gone.

    ``.claude/archive/`` is left out: it records past sessions as they were and is never edited.
    """
    assert lines_matching(FORMER_NAME, skipped_folders=ARCHIVE) == []

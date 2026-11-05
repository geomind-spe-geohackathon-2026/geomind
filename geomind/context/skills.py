"""Instructions a model loads when it needs them, from ``geomind/skills/<name>/SKILL.md``.

A skill file starts with frontmatter between ``---`` lines: ``name``, ``description`` (its one
line in the system prompt), ``tools`` (the tools it explains) and ``roles`` (the ``<team>/<name>``
of the agents that see it, comma-separated, or ``all``). The body after it is the how-to. Files
beside ``SKILL.md`` are extras the skill names, read as ``<skill>/<file>``.
"""

from functools import cache
from pathlib import Path

from geomind.errors import UnknownNameError
from geomind.utils.strings import did_you_mean, join_names

SKILLS = Path(__file__).parent.parent / "skills"
FIELDS = ("name", "description", "tools", "roles")
ALL = "all"


def _parsed(path):
    """Return ``(fields, body)`` of one ``SKILL.md``; a file without its frontmatter raises."""
    text = path.read_text()
    head, marker, body = text.removeprefix("---\n").partition("\n---\n")
    if not text.startswith("---\n") or not marker:
        raise UnknownNameError(f"skills: file = {path}; expected frontmatter between --- lines")
    fields = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        if key.strip():
            fields[key.strip()] = value.strip()
    missing = [name for name in FIELDS if not fields.get(name)]
    if missing or fields["name"] != path.parent.name:
        raise UnknownNameError(
            f"skills: file = {path}; expected {', '.join(FIELDS)} and name = its folder"
        )
    roles = tuple(role.strip() for role in fields["roles"].split(",") if role.strip())
    return {**fields, "roles": roles}, body.strip()


@cache
def _skills():
    """Return ``{name: (fields, body)}`` of every skill folder, sorted by name."""
    return {path.parent.name: _parsed(path) for path in sorted(SKILLS.glob("*/SKILL.md"))}


def skill_names(role=None):
    """Return the names of the skills ``role`` sees (every skill for ``None``), sorted."""
    return [
        name
        for name, (fields, _) in _skills().items()
        if role is None or ALL in fields["roles"] or role in fields["roles"]
    ]


def load_skill(name, role=None):
    """Return the text of one skill, or one extra file as ``<skill>/<file>``.

    An unknown name, or a skill ``role`` does not have, raises with the skills it has.
    """
    skill, _, extra = name.partition("/")
    names = skill_names(role)
    if skill not in names:
        known = skill in _skills()
        reason = "is not a skill of this role" if known else "is no skill"
        raise UnknownNameError(
            f"read_skill: name = {name!r} {reason}; expected one of {join_names(names)}"
            f"{'' if known else did_you_mean(skill, names)}"
        )
    if not extra:
        return _skills()[skill][1]
    files = sorted(
        path.name
        for path in (SKILLS / skill).iterdir()
        if path.is_file() and path.name != "SKILL.md"
    )
    if extra not in files:
        raise UnknownNameError(
            f"read_skill: name = {name!r}; expected {skill} or one of its files: "
            f"{join_names(files) if files else 'none'}"
        )
    return (SKILLS / skill / extra).read_text().strip()


def skill_description(name):
    """Return the one line of a skill, from its frontmatter."""
    return _skills()[name][0]["description"]


def _explains(fields, tools):
    """Tell whether a skill is for an agent with ``tools``: its ``tools`` field names one of them.

    A ``tools`` field in words (``every tool that takes a quantity``) fits every agent.
    """
    named = [item.strip() for item in fields["tools"].split(",") if item.strip()]
    if tools is None or not all(item.isidentifier() for item in named):
        return True
    return any(item in tools for item in named)


def skill_listing(role=None, tools=None):
    """Return what the system prompt says about the skills ``role`` sees: names with one line.

    With ``tools`` (the names an agent is offered), a skill that names only tools the agent lacks
    is left out of the list; ``read_skill`` still reads it.
    """
    names = [name for name in skill_names(role) if _explains(_skills()[name][0], tools)]
    lines = [f"- {name}: {skill_description(name)}" for name in names]
    return "\n".join(["Skills you can read with read_skill:", *lines]) if lines else ""


def skill_hint(name):
    """Return the words a tool error ends with to point at a skill."""
    return f"read_skill('{name}') for the rules"


def tool_skills():
    """Return ``{tool name: skill name}`` from every skill's ``tools`` field (identifiers only)."""
    found = {}
    for name, (fields, _) in _skills().items():
        for item in fields["tools"].split(","):
            item = item.strip()
            if item.isidentifier():
                found.setdefault(item, name)
    return found


SKILL_MARK = "[skill {name}, sent with the first call of {tool}]"
"""The line that opens a skill attached to a tool's first result; the loop looks for it."""


def first_call_skill(tool, messages):
    """Return the skill text to attach to ``tool``'s result, or ``None`` when already shown.

    A skill reaches a model only when loaded; an agent without ``read_skill`` (an engineer)
    never loads one. So the first result of a tool in an agent's conversation carries what
    explains it, once: the skill's opening part (before its first tool section) with this tool's
    own ``### `tool``` section; a later first call of another tool of the skill carries only its
    section (``SECTION_MARK``). The other tools' sections are not sent: the whole skill stayed in
    the history for the run, 15 % of the case lead's input (QA-273). A call after ``read_skill``
    of that skill gets none.
    """
    name = tool_skills().get(tool)
    if name is None:
        return None
    opening = f"[skill {name}, sent with the first call of "
    section_mark = SECTION_MARK.format(name=name, tool=tool)
    shown = False
    for message in messages:
        text = str(getattr(message, "content", ""))
        if section_mark in text or f"{opening}{tool}]" in text:
            return None
        shown = shown or opening in text
        for call in getattr(message, "tool_calls", None) or ():
            if getattr(call, "name", None) == "read_skill" and name in str(
                getattr(call, "input", "")
            ):
                return None
    section = tool_section(tool)
    if shown:
        return f"{section_mark}\n{section}" if section else None
    body = _skills()[name][1]
    if not section:
        return f"{SKILL_MARK.format(name=name, tool=tool)}\n{body}"
    intro = body.split("\n### ", 1)[0].strip()
    rest = WHOLE_SKILL.format(name=name)
    return (
        f"{SKILL_MARK.format(name=name, tool=tool)}\n{intro}\n\n### `{tool}`\n{section}\n\n{rest}"
    )


SECTION_MARK = "[skill {name}, section of {tool}]"
"""The line that opens the section of a tool whose skill an earlier result already opened."""
WHOLE_SKILL = "(The other tools' sections of this skill: read_skill('{name}').)"
"""The pointer to the whole skill after a first result's part of it."""


def tool_section(tool):
    """Return the ``### `tool``` section of the skill that explains ``tool``, without its heading.

    A tool whose call is a question to the user (``ask_user``, ``ask_economics``) returns no result
    the skill could come with, so its description carries this section: the skill stays the one
    place the usage is written, and the description is made from it.
    """
    name = tool_skills().get(tool)
    if name is None:
        return ""
    body = _skills()[name][1]
    heading = f"### `{tool}`"
    if heading not in body:
        return ""
    section = body.split(heading, 1)[1]
    for end in ("\n### ", "\n## "):
        section = section.split(end, 1)[0]
    return section.strip()

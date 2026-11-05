"""The stored references the gemini tools take: their schemas, their listing and their errors.

A reference is ``<kind>/<name>``: a design the tools stored, a run ``result/<id>`` or a study. The
schema of an argument carries a ``pattern`` and one example, but the pattern is not enforced when
the call is validated: a wrong reference reaches the tool, which answers with the stored references
of the kind in the chat.
"""

import re

from geomind.errors import ToolError
from geomind.utils.strings import join_names

NAME = "[A-Za-z0-9._-]+"
EXAMPLES = {
    "design": (
        "design/<name>",
        "design/boiler_only",
        "a tool returned it, for example build_plant",
    ),
    "result": ("result/<id>", "result/3f9a1c2d4e5b6a78", "simulate returned it"),
    "study": ("study/<name>", "study/sized", "a study tool returned it or list_studies listed it"),
}
INDEXES = {"design": "designs.index", "result": "results.index"}
STUDY_INDEX = "studies.index"
REFERENCE = re.compile(rf"^(?:design|result|study)/{NAME}$")


def reference_schema(kind, *, many=False, optional=False):
    """Return the function that gives the JSON Schema of an argument holding stored references.

    ``many`` is a list of references, ``optional`` one that may be ``null``. The schema has the
    kind's ``pattern`` and a description with one example.
    """
    form, example, origin = EXAMPLES[kind]
    single = {"type": "string", "pattern": f"^{kind}/{NAME}$", "examples": [example]}
    description = f"A stored {kind} reference such as '{example}' ({form}); {origin}."

    def schema():
        if many:
            return {"type": "array", "items": single, "description": description}
        if optional:
            return {
                "anyOf": [single, {"type": "null"}],
                "default": None,
                "description": description,
            }
        return {**single, "description": description}

    return schema


async def index_reference(context, kind, reference):
    """Add ``reference`` to the index of its kind, which ``stored_references`` lists from."""
    key = INDEXES[kind]
    async with context.session.index_lock:
        kept = context.session.load_artifact(key) or {"references": []}
        if reference in kept["references"]:
            return
        references = [*kept["references"], reference]
        await context.session.save_artifact(key, {"references": references})


def is_index(key):
    """Tell whether an artifact key is one of the chat's reference indexes, which grow."""
    return key == STUDY_INDEX or key in INDEXES.values()


def without_references(key, index, dropped):
    """Return the index stored at ``key`` without the references of ``dropped``."""
    if key == STUDY_INDEX:
        return {**index, "studies": [e for e in index["studies"] if e["study"] not in dropped]}
    return {**index, "references": [r for r in index["references"] if r not in dropped]}


def references_in(value):
    """Return every stored reference a tool output holds, at any depth."""
    if isinstance(value, str):
        return {value} if REFERENCE.match(value) else set()
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return set().union(*(references_in(item) for item in value))
    return set()


def studied_designs(context):
    """Return the design references the stored studies read and wrote (chats before the index)."""
    found = []
    for entry in (context.session.load_artifact(STUDY_INDEX) or {"studies": []})["studies"]:
        record = context.session.load_artifact(entry["study"]) or {"designs": {}}
        found += [*record["designs"].get("read", []), *record["designs"].get("wrote", [])]
    return found


def stored_references(context, kind):
    """Return the references of a kind that exist in this chat, oldest first."""
    if kind == "study":
        entries = (context.session.load_artifact(STUDY_INDEX) or {"studies": []})["studies"]
        return [entry["study"] for entry in entries]
    listed = (context.session.load_artifact(INDEXES[kind]) or {"references": []})["references"]
    older = studied_designs(context) if kind == "design" else []
    return [reference for reference in dict.fromkeys([*listed, *older])]


def unknown_reference(context, kind, given, where, field):
    """Return the ``unknown_name`` error of a reference that is not stored, listing those that are.

    A name given without its ``<kind>/`` prefix that matches a stored one is named as the likely
    intent.
    """
    form, example, origin = EXAMPLES[kind]
    stored = stored_references(context, kind)
    listing = join_names(stored) if stored else f"none stored yet in this chat for {kind}"
    likely = f"{kind}/{given}"
    hint = f"; did you mean {likely!r}?" if likely in stored else ""
    if kind == "result":
        hint += project_result_hint(context, given)
    if kind == "design":
        hint += (
            "; a plant of the project (Plant page, earlier chat) is design/<its name> or "
            "design/v<version>, as list_plants names them"
        )
    return ToolError(
        f"{where}: {field} = {given!r}; expected a reference of the form '{form}' such as "
        f"'{example}' ({origin}); stored {kind} references: {listing}{hint}",
        code="unknown_name",
        path=field,
    )


def project_result_hint(context, given):
    """Return how to use a result of the project's Study page, which no result tool reads (QA-165).

    ``list_studies`` lists such a result under ``project_study`` with its ``kpis`` and
    ``checks``; its series are only in a new run of its plant version.
    """
    workspace = context.session.workspace
    read = getattr(workspace, "project_designs", None)
    if read is None or context.project is None:
        return ""
    found = read(context.project) or {}
    wanted = str(given).removeprefix("result/")
    for study in found.get("studies") or []:
        result = study.get("result") or {}
        if str(result.get("id")) == wanted:
            version = result.get("plant_version") or study.get("plant_version")
            return (
                f"; {given!r} is a result of the project's study {study.get('name')!r}, not of "
                "this chat: quote its `kpis` and `checks` from list_studies (project_study), and "
                f"for its series or a new check simulate design/v{version} and read that result"
            )
    return (
        "; a result listed by list_studies under project_study is not readable by the result "
        "tools: quote its kpis and checks, or simulate its plant (design/v<plant_version>)"
    )

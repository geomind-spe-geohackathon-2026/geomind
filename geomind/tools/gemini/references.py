"""The stored references the gemini tools take: their schemas, their listing and their errors.

A reference is ``<kind>/<name>``: a design the tools stored, a run ``result/<id>`` or a study. The
schema of an argument carries a ``pattern`` and one example, but the pattern is not enforced when
the call is validated: a wrong reference reaches the tool, which answers with the stored references
of the kind in the chat.
"""

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
    kept = context.session.load_artifact(key) or {"references": []}
    if reference in kept["references"]:
        return
    await context.session.save_artifact(key, {"references": [*kept["references"], reference]})


def studied_designs(context):
    """Return the design references the stored studies read and wrote (chats before the index)."""
    found = []
    for entry in (context.session.load_artifact("studies.index") or {"studies": []})["studies"]:
        record = context.session.load_artifact(entry["study"]) or {"designs": {}}
        found += [*record["designs"].get("read", []), *record["designs"].get("wrote", [])]
    return found


def stored_references(context, kind):
    """Return the references of a kind that exist in this chat, oldest first."""
    if kind == "study":
        entries = (context.session.load_artifact("studies.index") or {"studies": []})["studies"]
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
    return ToolError(
        f"{where}: {field} = {given!r}; expected a reference of the form '{form}' such as "
        f"'{example}' ({origin}); stored {kind} references: {listing}{hint}",
        code="unknown_name",
        path=field,
    )

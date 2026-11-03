"""The smallest case and plant file of gemini's public schemas, for a model that lacks a header."""

import json


def skeleton_of(schema, name):
    """Return the smallest value of a JSON Schema: its constant, its required keys, or a name."""
    if "const" in schema:
        return schema["const"]
    if schema.get("type") == "object" and schema.get("required"):
        properties = schema.get("properties", {})
        return {key: skeleton_of(properties.get(key, {}), key) for key in schema["required"]}
    return f"<{name}>"


def case_skeleton():
    """Return the smallest case gemini's public schema accepts the shape of, from ``Case.schema``.

    Its constants are gemini's own (``format``, ``kind``) and every other required leaf is named,
    such as ``"<start>"``: the model fills them, geomind invents no value.
    """
    import gemini as gm

    return skeleton_of(gm.Case.schema(), "case")


def plant_skeleton():
    """Return the smallest plant file gemini's public schema accepts, from ``gm.plants.schema``."""
    import gemini as gm

    return skeleton_of(gm.plants.schema(), "plant")


def requirement_shape():
    """Return the ``set_case`` argument of one requirement, its fields from gemini's schema.

    A field with options lists them (``doublet|heat_pump|...``), any other names its type; the
    requirement's name is the key, as ``set_case`` ``requirements`` takes it.
    """
    import gemini as gm

    item = gm.Case.schema()["properties"]["requirements"]["items"]
    properties = item["properties"]

    def shown(key):
        options = properties[key].get("enum")
        return "|".join(options) if options else f"<{properties[key].get('type', key)}>"

    fields = {key: shown(key) for key in properties if key != "name"}
    required = ", ".join(key for key in item["required"] if key != "name")
    return f"requirements={{'<name>': {fields!r}}}, each with {required}"


QUANTITY_KEYS = ("range", "uncertainty")
"""Keys every ``{value, unit}`` takes beside them, named once in a tree, not on every line."""


def schema_tree(schema, path=""):
    """Return one line per field of a JSON Schema: path, form, units or options, ``*`` if needed.

    A quantity is ``{value, unit}`` with its accepted units; a series is that or ``{file, column,
    unit}``; a list of objects is ``path[]`` with its fields; an option list is ``a|b|c``.
    """
    lines = []
    for key, sub in (schema.get("properties") or {}).items():
        mark = "*" if key in (schema.get("required") or ()) else ""
        lines.extend(field_lines(sub, f"{path}{key}{mark}", f"{path}{key}"))
    return lines


def field_lines(schema, shown, path):
    """Return the lines of one field: itself when it is a leaf, else its fields."""
    form = leaf_form(schema)
    if form is not None:
        return [f"{shown}: {form}"]
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        return [f"{shown}[]:", *("  " + line for line in schema_tree(schema["items"]))]
    if schema.get("properties"):
        return schema_tree(schema, f"{path}.")
    if schema.get("additionalProperties") not in (None, False):
        return [f"{shown}: {{name: {leaf_form(schema['additionalProperties']) or 'object'}}}"]
    return [f"{shown}: {schema.get('type', 'object')}"]


def leaf_form(schema):
    """Return the form of a leaf field, or ``None`` for one with fields of its own."""
    if "anyOf" in schema:
        forms = [leaf_form(item) or "object" for item in schema["anyOf"]]
        return " or ".join(dict.fromkeys(forms))
    if "enum" in schema:
        return "|".join(str(item) for item in schema["enum"])
    if "const" in schema:
        return json.dumps(schema["const"])
    properties = schema.get("properties") or {}
    if "value" in properties and "unit" in properties:
        units = properties["unit"].get("enum") or schema.get("x-units")
        return "{value, unit} in " + "|".join(units) if units else "{value, unit}"
    if "value" in properties and len(set(properties) - set(QUANTITY_KEYS)) == 1:
        return f"{{value}} ({properties['value'].get('type', 'value')})"
    if "file" in properties and "column" in properties:
        units = (properties.get("unit") or {}).get("enum")
        extra = ", time_zone" if "time_zone" in properties else ""
        shown = f" in {'|'.join(units)}" if units else ""
        return f"{{file, column, unit{extra}}}{shown}"
    if schema.get("type") in ("string", "number", "integer", "boolean"):
        return schema["type"]
    return None


def case_tree():
    """Return the case's key tree from gemini's public ``Case.schema()``, as prompt text."""
    import gemini as gm

    lines = [line for line in schema_tree(gm.Case.schema()) if not line.endswith("about: object")]
    note = (
        "## Case keys\n\nThe keys of the case, from gemini's schema: * marks a required key, "
        "every {value, unit} also takes range and uncertainty, and every section takes about."
    )
    return "\n".join([note, *lines])

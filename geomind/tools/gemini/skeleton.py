"""The smallest case and plant file of gemini's public schemas, for a model that lacks a header."""


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

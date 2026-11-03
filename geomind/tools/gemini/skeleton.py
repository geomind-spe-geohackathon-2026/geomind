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

"""The smallest case and plant file of gemini's public schemas, for a model that lacks a header."""

import json
import re

from geomind.errors import UnknownNameError


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
        items = schema["items"]
        if not items.get("properties"):
            return [f"{shown}[]: {leaf_form(items) or items.get('type', 'object')}"]
        return [f"{shown}[]:", *("  " + line for line in schema_tree(items))]
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


def key_tree(schema):
    """Return the compact key tree of any gemini public JSON Schema, one line per field.

    A nested ``about`` (free notes of a section) is said once in the heading instead.
    """
    return [
        line for line in schema_tree(schema) if not (".about" in line and line.endswith("object"))
    ]


def schemas_of(name):
    """Return ``[(label, schema)]`` of one tree: gemini's public schemas, read now."""
    import gemini as gm

    if name in ("case", "case_compact"):
        return [
            ("", gm.Case.schema()),
            ("Economics (set_case economics=...):", gm.case.Economics.schema()),
        ]
    if name == "plant":
        return [("", gm.plants.schema())]
    if name == "study":
        return [("", gm.study.Study.schema())]
    raise UnknownNameError(
        f"key tree: name = {name!r}; expected case, case_compact, plant or study"
    )


TREE_HEADINGS = {
    "case": (
        "## Case keys\n\nThe keys of the case and of its economics, from gemini's schemas: these "
        "are all the keys, so never read the schema. * marks a required key, every {value, unit} "
        "also takes range and uncertainty, and every section takes about. After each key: what "
        "it means and where its value comes from (brief, data, report, user, economics); "
        "derived means gemini computes it, so leave it unset."
    ),
    "case_compact": (
        "## Case keys\n\nThe keys of the case and of its economics, from gemini's schemas: these "
        "are all the keys, so never read the schema. * marks a required key, every {value, unit} "
        "also takes range and uncertainty, and every section takes about; a wrong unit comes "
        "back from `set_case` with the accepted ones. After each key, in brackets: where its "
        "value comes from (brief, data, report, user, economics); derived "
        "means gemini computes it, so leave it unset. `describe_case(path)` gives what each key "
        "under a path means, such as `site.air`, `demand.cooling` or `economics.capex`."
    ),
    "plant": (
        "## Plant file keys\n\nThe keys of a plant file, from gemini's schema; "
        "`read_plant(plant_class=...)` gives a class's whole file and `describe_module` a "
        "module's parameters (* has no default), units and ports:"
    ),
    "study": (
        "## Study keys\n\nThe keys of a study file (`run_study`, `optimize`), from gemini's "
        "schema; * marks a required key:"
    ),
}
"""The heading of each tree in a system prompt."""


def described(lines, fields):
    """Return the tree's lines with each field's meaning after it, where geomind has one.

    A meaning that holds for a group (every ``capex.`` field) is said on the group's first line.
    """
    from geomind.tools.gemini.fields import meaning

    shown, parent, last = [], "", None
    for line in lines:
        path = line.strip().split(":", 1)[0].replace("*", "")
        if line.endswith("[]:"):
            parent = path.removesuffix("[]")
        elif not line.startswith("  "):
            parent = ""
        full = f"{parent}.{path}" if line.startswith("  ") and parent else path.removesuffix("[]")
        text = meaning(full, fields)
        if text and text == last:
            text = None
        last = text or last
        shown.append(f"{line} — {text}" if text else line)
    return shown


SOURCE_TAGS = ("brief", "report", "data", "user", "economics", "econ")
"""The words that say where a case value comes from, at the end of a field's meaning."""


def source_tag(meaning_text):
    """Return where a field's value comes from, from its meaning: ``brief/report``, ``derived``.

    ``None`` when the meaning names no source.
    """
    if not meaning_text:
        return None
    if "derived" in meaning_text:
        return "derived"
    last = meaning_text.rsplit(";", 1)[-1].split("(")[0].strip()
    words = last.split("/")
    return last if last and all(word in SOURCE_TAGS for word in words) else None


UNIT_LIST = re.compile(r" in [^ ]+")
"""The accepted units of a form, `` in K/km|K/m``: ``describe_case`` and ``set_case`` give them."""


def compact(lines):
    """Return described lines with each meaning cut to its source tag and no unit lists."""
    shown = []
    for line in lines:
        key, _, meaning_text = line.partition(" — ")
        key = UNIT_LIST.sub("", key)
        tag = source_tag(meaning_text)
        shown.append(f"{key} [{tag}]" if tag else key)
    return shown


def described_tree(name):
    """Return ``[(label, lines)]`` of a tree, each case and economics line with its meaning."""
    from geomind.tools.gemini.fields import CASE_FIELDS, economics_fields

    found = []
    for label, schema in schemas_of(name):
        tree = key_tree(schema)
        if name in ("case", "case_compact"):
            tree = described(tree, economics_fields() if label else CASE_FIELDS)
        found.append((label, tree))
    return found


def tree_text(name):
    """Return one key tree as prompt text: its heading and the lines of each of its schemas.

    The case's tree says what each field means and where its value comes from, and what each
    option of the requirements means (``geomind/tools/gemini/fields.py``; an economics field by
    gemini's own description). ``case_compact`` says
    only where each value comes from; ``describe_case`` gives the meanings of one part.
    """
    from geomind.tools.gemini.fields import options_text

    lines = [TREE_HEADINGS[name]]
    for label, tree in described_tree(name):
        tree = compact(tree) if name == "case_compact" else tree
        lines.extend([*([""] if label else []), *([label] if label else []), *tree])
    if name in ("case", "case_compact"):
        lines.extend(["", options_text()])
    if name == "plant":
        import gemini as gm

        lines.extend(["", f"Module types: {', '.join(sorted(gm.modules.names()))}."])
    return "\n".join(lines)


def trees(*names):
    """Return the appendix of a prompt that holds the key trees ``names``, made when it renders."""

    def text():
        return "\n\n".join(tree_text(name) for name in names)

    return text


def case_tree():
    """Return the case's key tree, from gemini's ``Case`` and ``Economics`` schemas."""
    return tree_text("case")


def plant_tree():
    """Return the plant file's key tree from ``gm.plants.schema()`` and gemini's module types."""
    return tree_text("plant")


def field_line(name, field):
    """Return one parameter of a module description as a line: type, quantity, bounds, options.

    A list of quantities (``type: array`` in gemini 0.6.2's ``describe()``, request 14) reads
    ``{value: [<number>, ...], unit}``, the form gemini takes.
    """
    import gemini as gm

    mark = "*" if field.get("default") is None and field.get("enum") is None else ""
    listed = field.get("type") == "array"
    parts = [field.get("type") or "value"]
    if field.get("quantity"):
        units = gm.units.names(field["quantity"])
        form = "{value: [<number>, ...], unit}" if listed else "{value, unit}"
        parts.append(f"{form} {field['quantity']} in {'|'.join(units)}")
    if field.get("enum"):
        parts.append("|".join(str(item) for item in field["enum"]))
    bounds = [f">= {field['minimum']}" if field.get("minimum") is not None else ""]
    bounds.append(f"<= {field['maximum']}" if field.get("maximum") is not None else "")
    shown = " ".join(item for item in [*parts, *bounds] if item)
    note = (field.get("description") or "").split(";")[0]
    return f"{name}{mark}: {shown}" + (f" ({note})" if note else "")


def module_tree(description):
    """Return a module's compact description from gemini's ``describe()``.

    Its parameters and controls come one per line, its ports, outputs and children by name.
    """
    lines = [field_line(name, field) for name, field in description["parameters"].items()]
    controls = [field_line(name, field) for name, field in description["controls"].items()]
    return {
        "name": description["name"],
        "type": description["type"],
        "category": description["category"],
        "summary": description["summary"],
        "parameters": lines,
        "controls": controls,
        "inlets": {name: port.get("kind") for name, port in description["inlets"].items()},
        "outlets": {name: port.get("kind") for name, port in description["outlets"].items()},
        "outputs": sorted(description["outputs"]),
        "children": {
            name: child.get("type") if isinstance(child, dict) else child
            for name, child in description["children"].items()
        },
        "note": "* marks a parameter with no default: the plant file gives it",
    }


def lines_under(tree, wanted):
    """Return the lines of a tree whose key starts with ``wanted``, a list with its fields."""
    found, parent_wanted = [], False
    for line in tree:
        if not line.startswith("  "):
            parent_wanted = line.startswith(wanted)
        if parent_wanted:
            found.append(line)
    return found


def keys_under(path):
    """Return the described lines of the case tree under ``path``, with their units.

    ``economics.<key>`` reads the economics part; ``requirements`` adds what each option means.
    """
    from geomind.tools.gemini.fields import options_text

    economics = path == "economics" or path.startswith("economics.")
    wanted = path.removeprefix("economics").removeprefix(".")
    lines = []
    for label, tree in described_tree("case"):
        if bool(label) == economics:
            lines += lines_under(tree, wanted)
    if path.startswith("requirements"):
        lines.append(options_text())
    return lines


def module_reference(*names):
    """Return prompt text of gemini's own ``describe()`` of each module: its parameters, ports.

    Made when the prompt renders, so an agent's prompt follows gemini: a module gemini renames
    or drops is an error here, not a stale line in a prompt. A list parameter reads as gemini
    gives it; ``{"value": [..], "unit": "m"}`` is the form of a list of quantities.
    """
    import gemini as gm

    lines = ["## Module reference (from gemini)", ""]
    for name in names:
        tree = module_tree(gm.modules.get(name)().describe())
        lines.append(f"### {tree['type']} ({tree['category']}): {tree['summary']}")
        lines += [f"- {line}" for line in tree["parameters"] + tree["controls"]]
        ports = [f"in {key} ({kind})" for key, kind in tree["inlets"].items()]
        ports += [f"out {key} ({kind})" for key, kind in tree["outlets"].items()]
        lines.append(f"- ports: {', '.join(ports) or 'none'}")
        lines.append("")
    lines.append("* marks a parameter with no default: the plant file gives it.")
    return "\n".join(lines)


def modules_of(*categories):
    """Return gemini's module names in ``categories``, such as ``wells`` or ``subsurface``."""
    import gemini as gm

    return sorted(
        name
        for name in gm.modules.names()
        if getattr(gm.modules.get(name), "category", None) in categories
    )

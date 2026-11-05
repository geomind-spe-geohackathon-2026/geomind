"""What ``evaluate_module`` fixes and fills before gemini's call (IMP-012, IMP-013).

A slip of form, not of value, is fixed here with a note in the answer: a module type written in
another case or in snake case, a module id of the named design for its type, a control given as a
parameter (or a parameter as a control), ``inlets`` given as an empty list. Values are only ever
taken from the named design or result, never made up.
"""

import copy
from datetime import datetime, timezone

from geomind.errors import ToolError


def module_type(gm, name, plant_data):
    """Return ``(type name, module path or None, note or None)`` of the ``name`` a call gives."""
    names = gm.modules.names()
    if name in names:
        return name, None, None
    entry = module_entry(plant_data, name)
    if isinstance(entry, dict) and entry.get("type") in names:
        kind = entry["type"]
        return kind, name, f"name {name!r} is the design's module of type {kind}: evaluated as {kind}"
    folded = {item.replace("_", "").lower(): item for item in names}
    found = folded.get(str(name).replace("_", "").replace(" ", "").lower())
    if found is not None:
        return found, None, f"name {name!r} is gemini's module type {found!r}"
    return name, None, None


def module_entry(plant_data, path):
    """Return the ``modules`` entry of a dotted module path of a plant file, or ``None``."""
    node = {"modules": (plant_data or {}).get("modules") or {}}
    for part in str(path).split("."):
        node = (node.get("modules") or {}).get(part) if isinstance(node, dict) else None
    return node


def module_params(plant_data, path):
    """Return the ``params`` a plant file gives one module path, ``{}`` when none."""
    node = (plant_data or {}).get("params") or {}
    for part in str(path).split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return copy.deepcopy(node) if isinstance(node, dict) else {}


PLANT_ONLY = ("range", "uncertainty", "options")
"""Keys of a plant file's value that a single call does not take."""


def bare_values(values, notes):
    """Return ``values`` with each ``{value, unit}`` stripped of its plant-file keys (range)."""
    kept = {}
    for key, value in (values or {}).items():
        if isinstance(value, dict) and "value" in value and any(k in value for k in PLANT_ONLY):
            value = {k: item for k, item in value.items() if k not in PLANT_ONLY}
            notes.append(f"{key}: its range is a plant-file key, dropped for one call")
        if isinstance(value, dict) and set(value) == {"value"}:
            value = value["value"]
            notes.append(f"{key}: a value with no unit is given bare in a call, {value!r}")
        kept[key] = value
    return kept


def placed_inputs(description, parameters, controls, notes):
    """Return ``(parameters, controls)`` with each name moved to the section that owns it."""
    owned_parameters = set(description["parameters"])
    owned_controls = set(description["controls"]) | set(description.get("boundaries") or {})
    parameters, controls = bare_values(parameters, notes), bare_values(controls, notes)
    for key in [key for key in parameters if key in owned_controls]:
        controls.setdefault(key, parameters.pop(key))
        notes.append(f"parameters.{key} is a control: moved to controls")
    for key in [key for key in controls if key in owned_parameters]:
        parameters.setdefault(key, controls.pop(key))
        notes.append(f"controls.{key} is a parameter: moved to parameters")
    return parameters, controls


def design_inputs(description, given, path, plant_data, notes):
    """Return ``(parameters, controls)``: the design's values of the module under the call's.

    ``given`` is ``(parameters, controls)`` of the call; each wins over the design's value.
    """
    parameters, controls = given
    own = bare_values(module_params(plant_data, path), [])
    sections = (
        (parameters, set(description["parameters"])),
        (controls, set(description["controls"]) | set(description.get("boundaries") or {})),
    )
    filled = []
    for section, names in sections:
        taken = {key: value for key, value in own.items() if key in names and key not in section}
        filled.append({**taken, **section})
        if taken:
            notes.append(f"from the design's {path}: {', '.join(sorted(taken))}")
    return filled[0], filled[1]


def stream_inlets(description):
    """Return the names of the module's required stream inlets."""
    return [
        port
        for port, item in description["inlets"].items()
        if item["port"].get("required") and item["port"].get("carrier") == "stream"
    ]


FIELDS = {"T": "temperature", "p": "pressure", "m_dot": "mass_flow"}
"""The stream fields of an inlet and the result fields they are read from."""


def peak_time(results, path, ports):
    """Return the ISO time of the step with the largest mass flow into the module's first port."""
    series = results.get(path, f"{ports[0]}.mass_flow")
    values = [abs(value) if value is not None else -1 for value in series["value"]]
    return series["time"][values.index(max(values))]


def result_inlets(results, path, description, inlets, time, notes):
    """Return ``inlets`` with T, p and m_dot of each required stream inlet read from a result.

    Each inlet keeps what the call gives (its ``fluid`` is the call's: a result keeps no fluid);
    the step is ``time``, or the step of the largest inflow when the call gives none.
    """
    ports = stream_inlets(description)
    if not ports:
        return inlets
    if time is None:
        time = peak_time(results, path, ports)
        notes.append(f"time not given: the step of the largest inflow into {path}, {time}")
    filled = {key: dict(value) for key, value in (inlets or {}).items()}
    for port in ports:
        stream = filled.setdefault(port, {})
        for field, name in FIELDS.items():
            if field in stream or (field == "m_dot" and "flow" in stream):
                continue
            moment = as_time(time)
            series = results.get(path, f"{port}.{name}", start=moment, end=moment)
            if not series["value"] or series["value"][0] is None:
                raise ToolError(
                    f"evaluate_module: the result has no {port}.{name} of {path} at {time}; "
                    "give that inlet's value in inlets, or another time",
                    code="missing_value",
                    path=f"inlets.{port}.{field}",
                )
            stream[field] = {"value": series["value"][0], "unit": series["unit"]}
    notes.append(f"inlets {', '.join(ports)}: T, p and m_dot from the result at {time}")
    return filled


def as_time(text):
    """Return an ISO 8601 text as an aware UTC time (a naive one taken as UTC)."""
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        raise ToolError(
            f"evaluate_module: time = {text!r}; expected an ISO 8601 time such as '2030-01-15'",
            path="time",
        ) from None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def plant_of(context, design, result):
    """Return ``(plant file in display units or None, results or None)`` a call names."""
    from geomind.tools.gemini.stored import load_design, load_run

    if result is not None:
        plant, _, results = load_run(context, result, "evaluate_module")
        return plant.to_dict(structure=True, units="display"), results
    if design is not None:
        plant = load_design(context, design, "evaluate_module")
        return plant.to_dict(structure=True, units="display"), None
    return None, None


def checked_type(gm, name, plant_data, notes):
    """Return the module type a call's ``name`` means, or raise ``unknown_name``."""
    import difflib

    kind, path, note = module_type(gm, name, plant_data)
    notes += [note] if note else []
    if kind not in gm.modules.names():
        raise ToolError(
            f"evaluate_module: name = {name!r}; expected a gemini module type (list_modules) or, "
            "with design or result, a module id of that plant",
            code="unknown_name",
            path="name",
            suggestions=difflib.get_close_matches(str(name), gm.modules.names()),
        )
    return kind, path


def listed_inlets(inlets):
    """Return ``inlets`` with an empty list as none; a list with items is refused."""
    if not isinstance(inlets, list):
        return inlets
    if inlets:
        raise ToolError(
            "evaluate_module: inlets is a list; expected an object {port: {fluid, T, p, m_dot}}",
            code="invalid_input",
            path="inlets",
        )
    return None


def prepared_call(context, name, given, design, result, time):
    """Return ``(type, description, parameters, inlets, controls, notes)`` of one call.

    ``given`` is the call's ``(parameters, inlets, controls)``; the design's or result's values
    fill what it leaves out, and each fix of form is named in ``notes``.
    """
    import gemini as gm

    notes = []
    parameters, inlets, controls = given
    plant_data, results = plant_of(context, design, result)
    kind, path = checked_type(gm, name, plant_data, notes)
    description = gm.modules.get(kind)().describe()
    inlets = listed_inlets(inlets)
    parameters, controls = placed_inputs(description, parameters, controls, notes)
    if path is not None:
        parameters, controls = design_inputs(
            description, (parameters, controls), path, plant_data, notes
        )
    if results is not None and path is not None:
        inlets = result_inlets(results, path, description, inlets, time, notes)
    return kind, description, parameters, inlets, controls, notes

"""The tools over gemini's module catalogue."""

import difflib
import json
from typing import Any

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.references import reference_schema


@tool(effect="read")
def list_modules(category: str | None = None):
    """List gemini's module types with category and summary.

    Skill `evaluating-a-module`.
    """
    import gemini as gm

    rows = []
    for name in gm.modules.names(category):
        description = gm.modules.get(name)().describe()
        rows.append(
            {
                "name": name,
                "category": description["category"],
                "summary": description["summary"],
            }
        )
    return rows


@tool(effect="read")
def describe_module(name: str):
    """Describe one module type: parameters, controls, ports, outputs.

    Skill `evaluating-a-module`.
    """
    import gemini as gm

    from geomind.tools.gemini.skeleton import module_tree

    return module_tree(gm.modules.get(name)().describe())


def checked_names(name, description, parameters, controls):
    """Raise ``invalid_input`` for a parameter or control the module does not have.

    A control given as a parameter is left to gemini, which raises ``invalid_call`` at
    ``parameters.<name>`` pointing to ``controls`` since 0.6.3 (request 27, #76). gemini names an
    unknown parameter only after the inlets are checked and has no check of ``controls``, so
    those stay here, with the names meant.
    """
    owned = {"parameters": set(description["parameters"]), "controls": set(description["controls"])}
    given = {"parameters": set(parameters or {}), "controls": set(controls or {})}
    unknown = given["parameters"] - owned["parameters"] - owned["controls"]
    for kind, keys in (
        ("parameters", unknown),
        ("controls", given["controls"] - owned["controls"]),
    ):
        for key in sorted(keys):
            where = (
                f"; it is a parameter of {name}: give it in `parameters`"
                if key in owned["parameters"] and kind == "controls"
                else f"; expected one of {', '.join(sorted(owned[kind])) or 'none'}"
            )
            raise ToolError(
                f"evaluate_module: {kind}.{key} is not a {kind[:-1]} of {name}{where}",
                code="invalid_input",
                path=f"{kind}.{key}",
                suggestions=difflib.get_close_matches(
                    key, sorted(owned["parameters"] | owned["controls"])
                ),
            )


def checked_inlets(name, description, inlets):
    """Raise ``invalid_input`` naming each required stream inlet a call leaves out, with its form.

    gemini says ``missing required inlet(s) source_in, sink_in``; the energy engineer sent the
    same call without ``inlets`` seven times (B2). The suggestion shows the form of each one.
    """
    missing = [
        port
        for port, item in description["inlets"].items()
        if item["port"].get("required")
        and item["port"].get("carrier") == "stream"
        and port not in (inlets or {})
    ]
    if not missing:
        return
    form = {
        "fluid": {"kind": "<brine, water, glycol_water, steam or gas>"},
        "T": {"value": "<number>", "unit": "degC"},
        "p": {"value": "<number>", "unit": "bar"},
        "m_dot": {"value": "<number>", "unit": "kg/s"},
    }
    raise ToolError(
        f"evaluate_module: inlets = {sorted(inlets or {})}; {name} needs the stream inlets "
        f"{', '.join(missing)}, each with its fluid, T, p and m_dot (or flow), from the case or "
        "the plant; or name the module's id with result=result/<id> to read T, p and m_dot of a "
        "simulated step (give only each inlet's fluid); read_skill('evaluating-a-module')",
        code="invalid_input",
        path="inlets",
        suggestions=[json.dumps({port: form for port in missing})],
    )


def plain(found):
    """Return ``found`` with every gemini ``Quantity`` in it as its ``{value, unit}`` dict."""
    import gemini as gm

    if isinstance(found, dict):
        return {key: plain(value) for key, value in found.items()}
    if isinstance(found, gm.units.Quantity):
        return found.to_dict()
    return found


@tool(
    effect="compute",
    late_schemas={
        "design": reference_schema("design", optional=True),
        "result": reference_schema("result", optional=True),
    },
)
def evaluate_module(
    context,
    name: str,
    parameters: dict[str, Any] | None = None,
    inlets: dict[str, dict[str, Any]] | list | None = None,
    controls: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    dt: dict[str, Any] | None = None,
    design: str | None = None,
    result: str | None = None,
    time: str | None = None,
):
    """Run one module at one point in display units.

    Skill `evaluating-a-module`.
    """
    import gemini as gm

    from geomind.tools.gemini.module_call import prepared_call

    kind, description, parameters, inlets, controls, notes = prepared_call(
        context, name, (parameters, inlets, controls), design, result, time
    )
    checked_names(kind, description, parameters, controls)
    checked_inlets(kind, description, inlets)
    called = gm.call(
        gm.modules.get(kind),
        parameters,
        inlets,
        controls,
        units="display",
        on_error="raise",
        state=state,
        dt=dt,
    )
    found = plain(called)
    return {**found, "notes": notes} if notes else found

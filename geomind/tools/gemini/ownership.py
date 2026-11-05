"""Which part of a plant file each engineer of the design team may change.

The process engineer owns the header, the type, the size and the modules; the integration
engineer owns the connections, the plant's boundaries and its ``bypass`` (how a module that is
off is bridged, gemini 0.6.2); the parameters belong to the discipline ``design.owners`` names
for their path prefix, as the process engineer recorded it.
A parameter path ``design.owners`` names no prefix of belongs to the discipline of its module's
gemini type (``OWNED_MODULES``, then the type's category), so an engineer can always write its
own part, owners recorded or not. The design lead, and any agent of no discipline, may change
everything.
"""

from functools import cache

from geomind.errors import ToolError

DISCIPLINES = ("process", "integration", "reservoir", "well", "energy")
SECTIONS = {
    "process": frozenset(
        {"format", "kind", "name", "about", "type", "size", "modules", "optional", "choices"}
    ),
    "integration": frozenset({"connections", "inlets", "outlets", "boundary", "fluids", "bypass"}),
}
"""The top-level keys of a plant file each discipline owns besides parameters."""
LEAF_KEYS = frozenset({"value", "unit", "min", "max", "options"})
PARAMS = "params."
STRUCTURE_KEYS = frozenset({"type", "modules"})
"""The keys of a module entry under ``modules``; any other key there is a parameter."""
OWNED_MODULES = {
    "reservoir": (
        "Doublet",
        "ProductionReservoir",
        "InjectionReservoir",
        "Formation",
        "ThermalDecline",
        "Degasser",
        "Filter",
        "Flare",
        "Desander",
    ),
    "well": ("Doublet", "ProductionWell", "InjectionWell", "ESP", "LineShaftPump"),
    "energy": (
        "HeatExchanger",
        "HeatPump",
        "Boiler",
        "ElectricBoiler",
        "CHP",
        "AbsorptionUnit",
        "AdsorptionChiller",
        "Cooler",
        "InjectionPump",
        "CirculationPump",
        "Pipe",
        "ThermalStorage",
    ),
}
"""The gemini module types whose parameters each discipline fills (``design.owners``)."""
CATEGORY_OWNERS = {
    "subsurface": "reservoir",
    "treatment": "reservoir",
    "wells": "well",
    "heating": "energy",
    "cooling": "energy",
    "exchangers": "energy",
    "storage": "energy",
    "pumps": "energy",
    "piping": "energy",
    "power": "energy",
}
"""The discipline of a gemini module category, for a type ``OWNED_MODULES`` does not list."""


def discipline_of(context):
    """Return the discipline of the agent that makes the call, or ``None``."""
    agent = getattr(context.session, "agent", None)
    return getattr(agent, "discipline", None)


def parameter_paths(params, prefix=""):
    """Return the dotted path of every parameter a ``params`` patch sets or removes."""
    if not isinstance(params, dict) or not params or set(params) & LEAF_KEYS:
        return [prefix] if prefix else []
    paths = []
    for key, value in params.items():
        path = f"{prefix}.{key}" if prefix else key
        paths.extend(parameter_paths(value, path) if value is not None else [path])
    return paths


def discipline_named(owner):
    """Return the discipline an owner of ``design.owners`` names, or the owner as it is.

    The process engineer writes an owner as a discipline (``reservoir``), as the engineer's tool
    name (``reservoir_engineer``, ``energy_systems_engineer``) or in words (``Reservoir
    engineer``); all name one discipline (QA-076: ``reservoir_engineer`` was refused its own part).
    """
    if not isinstance(owner, str):
        return owner
    words = owner.strip().lower().replace("-", "_").replace(" ", "_").split("_")
    for discipline in DISCIPLINES:
        if discipline in words:
            return discipline
    return owner


def owner_of(path, owners):
    """Return the discipline of the longest prefix of ``path`` in ``owners``, or ``None``.

    A prefix is a parameter path with or without its ``params.`` in front, as the process
    engineer may write either.
    """
    named = {key.removeprefix(PARAMS): discipline_named(owner) for key, owner in owners.items()}
    parts = path.split(".")
    for end in range(len(parts), 0, -1):
        owner = named.get(".".join(parts[:end]))
        if owner is not None:
            return owner
    return None


@cache
def _description(type_name):
    """Return the category and the children ``{name: type}`` of a gemini module type."""
    import gemini as gm

    from geomind.tools.gemini.skeleton import module_tree

    try:
        tree = module_tree(gm.modules.get(type_name)().describe())
    except (KeyError, ValueError, TypeError):
        return None, {}
    return tree["category"], tree["children"]


def type_disciplines(type_name):
    """Return the disciplines that fill the parameters of a gemini module type."""
    owned = frozenset(name for name, types in OWNED_MODULES.items() if type_name in types)
    if owned:
        return owned
    category = _description(type_name)[0]
    return frozenset({CATEGORY_OWNERS[category]}) if category in CATEGORY_OWNERS else frozenset()


def module_types(path, plant):
    """Return the gemini types of the modules along a parameter path, outermost first.

    The plant file's ``modules`` give the first level and any nested entries; a module type's own
    children (a ``Doublet``'s ``reservoir``, ``well``) come from gemini.
    """
    found, entries = [], (plant or {}).get("modules") or {}
    for part in path.split("."):
        entry = entries.get(part) if isinstance(entries, dict) else None
        if not isinstance(entry, dict) or not entry.get("type"):
            break
        found.append(entry["type"])
        children = _description(entry["type"])[1]
        entries = entry.get("modules") or {name: {"type": kind} for name, kind in children.items()}
    return found


def default_owners(path, plant):
    """Return the disciplines of the innermost module along ``path`` that has any."""
    for type_name in reversed(module_types(path, plant)):
        owned = type_disciplines(type_name)
        if owned:
            return owned
    return frozenset()


def foreign_parameters(params, discipline, owners, plant=None):
    """Return ``(path, owner)`` for each parameter of a patch that ``discipline`` does not own.

    ``design.owners`` decides a path it names a prefix of; any other path goes by its module's
    type in ``plant``.
    """
    found = []
    for path in parameter_paths(params):
        owner = owner_of(path, owners)
        if owner is None:
            defaults = default_owners(path, plant)
            if discipline in defaults:
                continue
            owner = next(iter(sorted(defaults)), None)
        if owner != discipline:
            found.append((f"params.{path}", owner))
    return found


def foreign_changes(changes, discipline, owners, plant=None):
    """Return ``(path, owner)`` for each part of ``changes`` that ``discipline`` does not own."""
    found = []
    for key, value in changes.items():
        if key == "params":
            found.extend(foreign_parameters(value, discipline, owners, plant))
            continue
        owner = next((name for name, keys in SECTIONS.items() if key in keys), None)
        if owner != discipline:
            found.append((key, owner))
    return found


def _undotted(mapping):
    """Return ``mapping`` with each dotted key (``d0.well``) spelled as nested keys."""
    result = {}
    for key, value in mapping.items():
        parts = key.split(".") if isinstance(key, str) else [key]
        nested = value
        for part in reversed(parts[1:]):
            nested = {part: nested}
        result = _merged(result, {parts[0]: nested})
    return result


def _merged(target, patch):
    """Return ``target`` with ``patch``'s keys merged in, nested dicts merged key by key."""
    result = dict(target)
    for key, value in patch.items():
        both = isinstance(result.get(key), dict) and isinstance(value, dict)
        result[key] = _merged(result[key], value) if both else value
    return result


def placed_parameters(changes, plant):
    """Return ``changes`` with each module's parameters under ``params``, where gemini reads them.

    A model writes a module's parameters as ``{"d0": {...}}``, ``{"d0.well": {...}}``,
    ``{"modules": {"d0": {"well": {...}}}}`` or ``{"modules.heat_pump": {...}}``. Each is the
    same change as ``{"params": {"d0": ...}}``: a top-level key that names a module of the plant,
    and every key of a ``modules`` entry other than ``type`` and ``modules``, moves under
    ``params``. A section key (``size``, ``connections``) and a module's own ``type`` stay.
    """
    if not isinstance(changes, dict):
        return changes
    ids = set((plant or {}).get("modules") or {})
    placed, params = {}, {}
    for key, value in _undotted(changes).items():
        if key == "params" and isinstance(value, dict):
            params = _merged(params, _undotted(value))
        elif key == "modules" and isinstance(value, dict):
            modules = _module_entries(_undotted(value), ids)
            params = _merged(params, modules[1])
            if modules[0]:
                placed["modules"] = modules[0]
        elif key in ids and isinstance(value, dict):
            params = _merged(params, {key: value})
        else:
            placed[key] = value
    if params:
        placed["params"] = params
    return placed


def _module_entries(modules, ids):
    """Split a ``modules`` patch into its structure and the parameters written inside it."""
    structure, params = {}, {}
    for module, entry in modules.items():
        if module not in ids or not isinstance(entry, dict):
            structure[module] = entry
            continue
        kept = {key: value for key, value in entry.items() if key in STRUCTURE_KEYS}
        moved = {key: value for key, value in entry.items() if key not in STRUCTURE_KEYS}
        if kept:
            structure[module] = kept
        if moved:
            params[module] = moved
    return structure, params


def check_ownership(context, changes, where, plant=None):
    """Raise ``not_allowed`` when an engineer's patch reaches a part another discipline owns."""
    discipline = discipline_of(context)
    if discipline is None:
        return
    owners = (context.problem.design or {}).get("owners") or {}
    foreign = foreign_changes(changes, discipline, owners, plant)
    if not foreign:
        return
    path, owner = foreign[0]
    whose = f"the {owner} engineer's" if owner else "no discipline's (design.owners names none)"
    others = f" and {len(foreign) - 1} more" if len(foreign) > 1 else ""
    own = own_parts(discipline, owners)
    yours = f" Your parts: {', '.join(own)}." if own else ""
    raise ToolError(
        f"{where}: {path}{others} is {whose}; the {discipline} engineer changes only its own "
        f"part.{yours} Send the patch again with only your parts, and hand the rest back to the "
        "design lead with the reason, for its owner",
        code="not_allowed",
        path=f"changes.{path}",
        suggestions=own,
    )


def own_parts(discipline, owners):
    """Return the paths of ``design.owners`` that ``discipline`` owns, sorted (IMP-014)."""
    return sorted(
        key.removeprefix(PARAMS)
        for key, owner in (owners or {}).items()
        if discipline_named(owner) == discipline
    )

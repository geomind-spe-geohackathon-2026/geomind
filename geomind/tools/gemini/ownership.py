"""Which part of a plant file each engineer of the design team may change.

The process engineer owns the header, the type, the size and the modules; the integration
engineer owns the connections and the plant's boundaries; the parameters belong to the
discipline ``design.owners`` names for their path prefix, as the process engineer recorded it.
The design lead, and any agent of no discipline, may change everything.
"""

from geomind.errors import ToolError

DISCIPLINES = ("process", "integration", "reservoir", "well", "energy")
SECTIONS = {
    "process": frozenset({"format", "kind", "name", "about", "type", "size", "modules"}),
    "integration": frozenset({"connections", "inlets", "outlets", "boundary", "fluids"}),
}
"""The top-level keys of a plant file each discipline owns besides parameters."""
LEAF_KEYS = frozenset({"value", "unit", "min", "max", "options"})


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


def owner_of(path, owners):
    """Return the discipline of the longest prefix of ``path`` in ``owners``, or ``None``."""
    parts = path.split(".")
    for end in range(len(parts), 0, -1):
        owner = owners.get(".".join(parts[:end]))
        if owner is not None:
            return owner
    return None


def foreign_parameters(params, discipline, owners):
    """Return ``(path, owner)`` for each parameter of a patch that ``discipline`` does not own."""
    owned = [(f"params.{path}", owner_of(path, owners)) for path in parameter_paths(params)]
    return [(path, owner) for path, owner in owned if owner != discipline]


def foreign_changes(changes, discipline, owners):
    """Return ``(path, owner)`` for each part of ``changes`` that ``discipline`` does not own."""
    found = []
    for key, value in changes.items():
        if key == "params":
            found.extend(foreign_parameters(value, discipline, owners))
            continue
        owner = next((name for name, keys in SECTIONS.items() if key in keys), None)
        if owner != discipline:
            found.append((key, owner))
    return found


def check_ownership(context, changes, where):
    """Raise ``not_allowed`` when an engineer's patch reaches a part another discipline owns."""
    discipline = discipline_of(context)
    if discipline is None:
        return
    owners = (context.problem.design or {}).get("owners") or {}
    foreign = foreign_changes(changes, discipline, owners)
    if not foreign:
        return
    path, owner = foreign[0]
    whose = f"the {owner} engineer's" if owner else "no discipline's yet (design.owners names none)"
    others = f" and {len(foreign) - 1} more" if len(foreign) > 1 else ""
    raise ToolError(
        f"{where}: {path}{others} is {whose}; the {discipline} engineer changes only its own "
        "part. Hand it back to the design lead with the reason, for its owner",
        code="not_allowed",
        path=f"changes.{path}",
    )

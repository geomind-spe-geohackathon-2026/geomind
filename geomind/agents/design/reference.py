"""What each design agent knows of gemini, made from gemini when its prompt renders.

The modules each engineer owns come with gemini's own ``describe()`` (parameters, units, list
forms, ports), so it calls ``describe_module`` only for a module of another discipline. The
process engineer gets the plant classes with their summary and children, the integration
engineer every module's ports. A module gemini renames or drops is an error here, not a stale
line in a prompt.
"""

from geomind.tools.gemini.ownership import OWNED_MODULES
from geomind.tools.gemini.skeleton import module_reference, module_tree, trees


def engineer_appendix(discipline):
    """Return the appendix of an engineer: the plant file's keys and its own modules."""

    def text():
        owned = OWNED_MODULES[discipline]
        return f"{trees('plant')()}\n\n{module_reference(*owned)}"

    return text


def plant_catalogue():
    """Return each plant class of gemini with its summary, its children and its parameters."""
    import gemini as gm

    lines = ["## Plant classes (from gemini)", ""]
    for name in sorted(gm.plants.names()):
        tree = module_tree(gm.modules.get(name)().describe())
        children = ", ".join(f"{key}: {kind}" for key, kind in tree["children"].items())
        lines.append(f"- {name}: {tree['summary']} Children: {children or 'none'}.")
    return "\n".join(lines)


def ports_catalogue():
    """Return every module type of gemini with its ports and the fluid each carries."""
    import gemini as gm

    lines = ["## Module ports (from gemini): in <port> (<fluid>), out <port> (<fluid>)", ""]
    for name in sorted(gm.modules.names()):
        tree = module_tree(gm.modules.get(name)().describe())
        ports = [f"in {key} ({kind})" for key, kind in tree["inlets"].items()]
        ports += [f"out {key} ({kind})" for key, kind in tree["outlets"].items()]
        lines.append(f"- {name}: {', '.join(ports) or 'no ports'}")
    return "\n".join(lines)


def process_appendix():
    """Return the process engineer's appendix: the plant file's keys and the plant classes."""
    return f"{trees('plant')()}\n\n{plant_catalogue()}"


def integration_appendix():
    """Return the integration engineer's appendix: the plant file's keys and the module ports."""
    return f"{trees('plant')()}\n\n{ports_catalogue()}"

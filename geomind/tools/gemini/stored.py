"""The designs and runs a run keeps: how the gemini tools store them and read them back.

A design is a plant dict ``design/<name>``, ``gm.Plant.to_dict(structure=True)``, which keeps the
plant's inputs. A run ``result/<id>`` keeps its summary there and, beside it, ``<id>.results``
(``Results.to_bytes()``), ``<id>.plant`` (the plant dict that ran) and ``<id>.case`` (the case dict
it ran on, as the state held it). The id is a hash of the plant, the case, the contents of the
case's files and the run's options, so the same run has the same reference.
"""

import hashlib
import json
import re

from geomind.errors import ToolError
from geomind.tools.gemini.case import build_case, file_contents

DESIGN = "design/"
RESULT = "result/"
DESIGN_NAME = re.compile(r"[A-Za-z0-9._-]+")
RUN_PARTS = ("plant", "case", "results")


def check_design_name(name, where):
    """Raise unless ``name`` can name a stored design."""
    if not DESIGN_NAME.fullmatch(name):
        raise ToolError(
            f"{where}: name = {name!r}; expected letters, digits, '.', '_' or '-'", path="name"
        )


async def save_design(context, name, plant):
    """Store a gemini plant as ``design/<name>`` and return the reference."""
    check_design_name(name, "design")
    reference = f"{DESIGN}{name}"
    await context.session.save_artifact(reference, plant.to_dict(structure=True))
    return reference


def load_design(context, design, where):
    """Return a new gemini plant of a stored ``design/<name>``, or raise ``unknown_name``."""
    import gemini as gm

    data = context.session.load_artifact(design) if design.startswith(DESIGN) else None
    if data is None:
        raise ToolError(
            f"{where}: design = {design!r}; expected a reference such as 'design/<name>' that a"
            " tool returned",
            code="unknown_name",
            path="design",
        )
    return gm.Plant.from_dict(data)


def run_id(plant_data, case_data, files, options):
    """Return the id of a run: a hash of its plant dict, case dict, case files and options."""
    digests = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    text = json.dumps([plant_data, case_data, digests, options], sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


async def save_run(context, plant, results, summary, options):
    """Store a run of ``plant`` on the state's case; return its reference ``result/<id>``."""
    plant_data = plant.to_dict(structure=True)
    case_data = context.problem.case
    files = file_contents(context, case_data, {})
    identifier = run_id(plant_data, case_data, files, options)
    reference = f"{RESULT}{identifier}"
    await context.session.save_artifact(reference, summary)
    await context.session.save_artifact(f"{identifier}.results", results.to_bytes())
    await context.session.save_artifact(f"{identifier}.plant", plant_data)
    await context.session.save_artifact(f"{identifier}.case", case_data)
    return reference


def load_run(context, reference, where):
    """Return ``(plant, case, results)`` of a reference that ``save_run`` returned.

    The case is rebuilt from the case dict the run kept and the run's case files.
    """
    import gemini as gm

    identifier = reference.removeprefix(RESULT) if reference.startswith(RESULT) else ""
    parts = [context.session.load_artifact(f"{identifier}.{part}") for part in RUN_PARTS]
    if not identifier or None in parts:
        raise ToolError(
            f"{where}: reference = {reference!r}; expected a reference that simulate returned",
            code="unknown_name",
            path="reference",
        )
    plant_data, case_data, data = parts
    case = build_case(case_data, file_contents(context, case_data, {}))
    return gm.Plant.from_dict(plant_data), case, gm.Results.from_bytes(data)

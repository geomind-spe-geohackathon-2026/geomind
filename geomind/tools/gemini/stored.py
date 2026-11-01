"""The designs and runs a run keeps: how the gemini tools store them and read them back.

A design is a plant dict ``design/<name>``, ``gm.Plant.to_dict(structure=True)``, which keeps the
plant's inputs. A run ``result/<id>`` keeps its summary there and, beside it, ``<id>.results``
(``Results.to_bytes()``), ``<id>.plant`` (the plant dict that ran), ``<id>.case`` (the case dict it
ran on, as the state held it when the run read it) and ``<id>.files`` (``{file name: sha256}`` of
the case's files). Each file is kept once by its content as ``<sha256>.file``, so a file the case
names that is overwritten later never changes what an older run reads. The id is a hash of the
plant, the case, the files and the run's options, so the same run has the same reference.
"""

import hashlib
import json
import re

from geomind.errors import ToolError
from geomind.tools.gemini.case import build_case, file_contents, state_case

DESIGN = "design/"
RESULT = "result/"
DESIGN_NAME = re.compile(r"[A-Za-z0-9._-]+")
RUN_PARTS = ("plant", "case", "files", "results")
FILE = ".file"


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


def digests(files):
    """Return ``{file name: sha256}`` of ``{file name: bytes}``."""
    return {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}


def run_id(plant_data, case_data, files, options):
    """Return the id of a run: a hash of its plant dict, case dict, case files and options."""
    text = json.dumps([plant_data, case_data, digests(files), options], sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def ran_case(context):
    """Return ``(case dict, {file name: bytes})`` of the state's case, read once for one run.

    A run builds its case from this copy and ``save_run`` stores the same copy, so a ``set_case``
    in a parallel call cannot make the stored case differ from the one the run used.
    """
    data = state_case(context)
    return data, file_contents(context, data, {})


async def save_run(context, plant, results, summary, options, ran):
    """Store a run of ``plant`` on ``ran``, the case ``ran_case`` read; return ``result/<id>``."""
    plant_data = plant.to_dict(structure=True)
    case_data, files = ran
    identifier = run_id(plant_data, case_data, files, options)
    reference = f"{RESULT}{identifier}"
    session = context.session
    for content in files.values():
        await session.save_artifact(f"{hashlib.sha256(content).hexdigest()}{FILE}", content)
    await session.save_artifact(reference, summary)
    await session.save_artifact(f"{identifier}.results", results.to_bytes())
    await session.save_artifact(f"{identifier}.plant", plant_data)
    await session.save_artifact(f"{identifier}.case", case_data)
    await session.save_artifact(f"{identifier}.files", digests(files))
    return reference


def run_files(context, identifier):
    """Return ``{file name: bytes}`` of the case files a stored run kept."""
    named = context.session.load_artifact(f"{identifier}.files") or {}
    return {
        name: context.session.load_artifact(f"{digest}{FILE}") for name, digest in named.items()
    }


def load_run(context, reference, where):
    """Return ``(plant, case, results)`` of a reference that ``save_run`` returned.

    The case is rebuilt from the case dict and the case files the run kept.
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
    plant_data, case_data, _, data = parts
    case = build_case(case_data, run_files(context, identifier))
    return gm.Plant.from_dict(plant_data), case, gm.Results.from_bytes(data)

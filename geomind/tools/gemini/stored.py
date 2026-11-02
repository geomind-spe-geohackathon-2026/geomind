"""The designs and runs a run keeps: how the gemini tools store them and read them back.

A study ``study/<name>`` is the record of one study tool call (see ``save_study``);
``studies.index`` lists the studies of the chat, since a ``RunStore`` cannot list by prefix.

A design is a plant dict ``design/<name>``, ``gm.Plant.to_dict(structure=True)``, which keeps the
plant's inputs. A run ``result/<id>`` keeps its summary there and, beside it, ``<id>.results``
(``Results.to_bytes()``), ``<id>.plant`` (the plant dict that ran), ``<id>.case`` (the case dict it
ran on, as the state held it when the run read it) and ``<id>.files`` (``{file name: sha256}`` of
the case's files, series and economics). Each file is kept once by its content as
``<sha256>.file``, so a file the case names that is overwritten later never changes what an older
run reads. The id is a hash of the
plant, the case, the files and the run's options, so the same run has the same reference.
"""

import hashlib
import json
import re

from geomind.errors import ToolError
from geomind.tools.gemini.case import (
    build_case,
    digests,
    file_contents,
    keep_files,
    kept_files,
    state_case,
)
from geomind.types.events import StudyRecorded

DESIGN = "design/"
RESULT = "result/"
STUDY = "study/"
STUDY_INDEX = "studies.index"
DESIGN_NAME = re.compile(r"[A-Za-z0-9._-]+")
RUN_PARTS = ("plant", "case", "files", "results")


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
    await keep_files(context, files)
    await session.save_artifact(reference, summary)
    await session.save_artifact(f"{identifier}.results", results.to_bytes())
    await session.save_artifact(f"{identifier}.plant", plant_data)
    await session.save_artifact(f"{identifier}.case", case_data)
    await session.save_artifact(f"{identifier}.files", digests(files))
    return reference


def run_files(context, identifier):
    """Return ``{file name: bytes}`` of the case files a stored run kept."""
    return kept_files(context, context.session.load_artifact(f"{identifier}.files") or {})


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


def design_stem(design):
    """Return the name of a stored design reference, ``design/<name>`` without its prefix."""
    return design.rsplit("/", 1)[-1]


def case_id(ran):
    """Return the id of a case read by ``ran_case``: a hash of its dict and its files' digests."""
    text = json.dumps([ran[0], digests(ran[1])], sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def check_study_free(context, name, study, case, written, where):
    """Raise before a long study when ``study/<name>`` or a design it would write is taken.

    NOTE: the same study on the same case again is not refused, so a replay and a retry of a call
    that stored its study but failed to answer run again; ``save_study`` then finds the same
    content.
    """
    check_design_name(name, where)
    kept = context.session.load_artifact(f"{STUDY}{name}")
    if kept is not None and not (kept["study"] == study and kept["case"] == case):
        raise ToolError(
            f"{where}: name = {name!r}; {STUDY}{name} is taken by another study; use a new name",
            path="name",
        )
    if kept is not None:
        return
    for reference in written:
        if context.session.load_artifact(reference) is not None:
            raise ToolError(
                f"{where}: name = {name!r}; the design {reference} is taken; use a new name",
                path="name",
            )


def study_index(context):
    """Return the entries of ``studies.index``, oldest first; none before the first study."""
    return (context.session.load_artifact(STUDY_INDEX) or {"studies": []})["studies"]


async def save_study(context, name, tool, found, designs, best, case):
    """Store ``study/<name>``, add it to the index and send ``study.recorded``; return the key.

    ``found`` is ``(study dict, result dict)``: the gemini ``study.json`` that ran and gemini's
    plain form of what came back. ``designs`` is ``(read, wrote)``, the design references the
    study read and stored. The artifact keeps ``study``, ``result``, ``designs``
    (``{read, wrote}``), ``case`` (``case_id`` of the case it ran on), ``tool`` and ``versions``.
    The index keeps ``{study, tool, method, designs (plant names), best, case}`` of each, so
    ``list_studies`` needs no listing by prefix. NOTE: the index is read and written without a
    lock, so the study tools run alone.
    """
    study, result = found
    read, wrote = designs
    session = context.session
    key = f"{STUDY}{name}"
    record = {
        "study": study,
        "result": result,
        "designs": {"read": read, "wrote": wrote},
        "case": case,
        "tool": tool,
        "versions": session.versions(),
    }
    await session.save_artifact(key, record)
    plants = [design_stem(reference) for reference in read]
    entry = {"study": key, "tool": tool, "method": study["method"], "designs": plants}
    entry |= {"best": best, "case": case}
    kept = [item for item in study_index(context) if item["study"] != key]
    await session.save_artifact(STUDY_INDEX, {"studies": [*kept, entry]})
    await session.emit(
        StudyRecorded,
        run=session.state.run_id,
        index=session.state.step,
        call_id=context.call_id,
        study=key,
        tool=tool,
        method=study["method"],
        designs=plants,
        best=best,
    )
    return key


def load_study(context, study, where):
    """Return the record of a stored ``study/<name>``, or raise ``unknown_name``."""
    data = context.session.load_artifact(study) if study.startswith(STUDY) else None
    if data is None:
        raise ToolError(
            f"{where}: study = {study!r}; expected a reference such as 'study/<name>' that a tool"
            " returned or list_studies listed",
            code="unknown_name",
            path="study",
        )
    return data

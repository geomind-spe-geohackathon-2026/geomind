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

import contextvars
import hashlib
import json
import re

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.gemini.case import (
    build_case,
    digests,
    file_contents,
    keep_files,
    kept_files,
    state_case,
)
from geomind.tools.gemini.references import STUDY_INDEX, index_reference, unknown_reference
from geomind.types.events import StudyRecorded
from geomind.utils.json import to_jsonable

DESIGN = "design/"
RESULT = "result/"
STUDY = "study/"
DESIGN_NAME = re.compile(r"[A-Za-z0-9._-]+")
RUN_PARTS = ("plant", "case", "files", "results")


def check_design_name(name, where):
    """Raise unless ``name`` can name a stored design."""
    if not DESIGN_NAME.fullmatch(name):
        raise ToolError(
            f"{where}: name = {name!r}; expected letters, digits, '.', '_' or '-'", path="name"
        )


DRY_DESIGNS = contextvars.ContextVar("dry_designs", default=False)
"""Set while a plant tool's precheck runs: the call is checked whole and stores no design."""


def dry_precheck(function):
    """Return the precheck of a plant tool: the call run whole, with no design stored (IMP-018).

    The engine runs it before it asks the user to approve the call, so a write gemini refuses
    (a plant it cannot build, a part another engineer owns, a taken name) is refused at once.
    """

    async def precheck(context, **arguments):
        token = DRY_DESIGNS.set(True)
        try:
            await function(context, **arguments)
        finally:
            DRY_DESIGNS.reset(token)

    return precheck


async def save_design(context, name, plant):
    """Store a gemini plant as ``design/<name>`` and return the reference."""
    check_design_name(name, "design")
    reference = f"{DESIGN}{name}"
    if DRY_DESIGNS.get():
        return reference
    await context.session.save_artifact(reference, plant.to_dict(structure=True))
    await index_reference(context, "design", reference)
    return reference


def unquoted(reference):
    """Return a reference without the quotes a model may wrap it in, such as ``'"result/x"'``."""
    text = reference.strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'`":
        return text[1:-1].strip()
    return text


def load_design(context, design, where):
    """Return a new gemini plant of a stored ``design/<name>``, or raise ``unknown_name``."""
    import gemini as gm

    design = unquoted(design)
    data = context.session.load_artifact(design) if design.startswith(DESIGN) else None
    if data is None:
        raise unknown_reference(context, "design", design, where, "design")
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
    await index_reference(context, "result", reference)
    return reference


async def full_run(context, run, design, ran, options):
    """Return one study run as a page study stores it, its series kept as ``result/<id>`` (QA-088).

    ``{plant_name, case_name, design, result, report, run}``: ``design`` the stored design the run
    ended with, ``result`` the reference ``simulate`` would give (series, plant and case kept, so
    ``read_result`` and the backend read it), ``report`` gemini's evaluate report
    (``run.report.to_dict()``, display units) and ``run`` gemini's run record (``run.to_dict()``).
    """
    from geomind.tools.gemini.case import build_case
    from geomind.tools.gemini.runs import explained_report, run_summary

    case = build_case(*ran)
    summary = await runtime.in_gemini_thread(run_summary, run.plant, case, run.results, design)
    reference = await save_run(context, run.plant, run.results, summary, options, ran)
    return {
        "plant_name": run.plant_name,
        "case_name": run.case_name,
        "design": design,
        "result": reference,
        "report": explained_report(to_jsonable(run.report.to_dict())),
        "run": to_jsonable(run.to_dict()),
    }


def _simulated(plant, case):
    """Return ``(results, report)`` of a whole-year run of ``plant`` on ``case``."""
    import gemini as gm

    results = gm.simulate(plant, case)
    return results, gm.evaluate.report(plant, case, results)


async def simulated_run(context, design, ran, options):
    """Return the stored design ``design`` run on ``ran`` as ``full_run`` gives a study run (QA-088).

    For a study that ends with a design rather than gemini runs (size, optimize, evolve): the
    design is simulated once for the whole year. ``run`` is ``None``; a design that does not run
    gives ``{design, error}`` with gemini's message, and the study is kept.
    """
    import gemini as gm

    from geomind.tools.gemini.case import build_case
    from geomind.tools.gemini.runs import explained_report, run_summary

    plant = load_design(context, design, "study")
    case = build_case(*ran)
    try:
        results, report = await runtime.in_gemini_thread(_simulated, plant, case)
    except gm.errors.GeminiError as error:
        return {"design": design, "error": {"code": error.code, "message": str(error)[:500]}}
    summary = await runtime.in_gemini_thread(run_summary, plant, case, results, design)
    reference = await save_run(context, plant, results, summary, options, ran)
    return {
        "plant_name": design_stem(design),
        "case_name": case.name,
        "design": design,
        "result": reference,
        "report": explained_report(to_jsonable(report.to_dict())),
        "run": None,
    }


def run_files(context, identifier):
    """Return ``{file name: bytes}`` of the case files a stored run kept."""
    return kept_files(context, context.session.load_artifact(f"{identifier}.files") or {})


def load_run(context, reference, where):
    """Return ``(plant, case, results)`` of a reference that ``save_run`` returned.

    The case is rebuilt from the case dict and the case files the run kept.
    """
    import gemini as gm

    reference = unquoted(reference)
    identifier = reference.removeprefix(RESULT) if reference.startswith(RESULT) else ""
    parts = [context.session.load_artifact(f"{identifier}.{part}") for part in RUN_PARTS]
    if not identifier or None in parts:
        raise unknown_reference(context, "result", reference, where, "reference")
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


async def save_study(context, name, tool, found, designs, best, case, runs=None):
    """Store ``study/<name>``, add it to the index and send ``study.recorded``; return the key.

    ``found`` is ``(study dict, result dict)``: the gemini ``study.json`` that ran and gemini's
    plain form of what came back. ``designs`` is ``(read, wrote)``, the design references the
    study read and stored. The artifact keeps ``study``, ``result``, ``designs``
    (``{read, wrote}``), ``case`` (``case_id`` of the case it ran on), ``tool`` and ``versions``,
    and, when the study ran plants on the case, ``runs``: per run the full outcome as a page study
    of the backend stores it (``full_run``), so the Results tab shows agent studies too (QA-088).
    The index keeps ``{study, tool, method, designs (plant names), best, case}`` of each, so
    ``list_studies`` needs no listing by prefix. NOTE: the study tools run alone within a run, and
    the index lock keeps runs side by side from losing an entry.
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
        **({"runs": runs} if runs is not None else {}),
    }
    await session.save_artifact(key, record)
    plants = [design_stem(reference) for reference in read]
    entry = {"study": key, "tool": tool, "method": study["method"], "designs": plants}
    entry |= {"best": best, "case": case}
    async with session.index_lock:
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
        raise unknown_reference(context, "study", study, where, "study")
    return data

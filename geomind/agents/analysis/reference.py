"""The gemini part of the analysis team's prompts, made from gemini when a prompt renders.

The metric names, titles, units and which ones a study may minimise come from
``gm.evaluate.metrics()``; the economics keys, their units and meanings from gemini's
``Economics`` schema and geomind's field texts (``geomind/tools/gemini/fields.py``). A name gemini
changes changes here, never in a hand-written line.
"""

STUDY_KPIS = ("heating_coverage", "cooling_coverage", "cop", "peak_heat", "peak_cold")
"""The metrics a study reads besides the objectives; gemini keeps them in a private module
(``gemini.study._utils.trial.KPI_NAMES``), so a test pins them: gemini request C-1."""

HEADING = (
    "## gemini reference for the analysis team\n\n"
    "Made from gemini when this prompt renders: use these names exactly, and the units gemini "
    "gives; never convert a unit or work out a value yourself."
)


def metrics():
    """Return gemini's metrics, ``[{name, title, unit, objective}]``, in gemini's order."""
    import gemini as gm

    return list(gm.evaluate.metrics())


def metrics_text():
    """Return one line per metric: its name, title, display unit, and whether it is an objective."""
    lines = [
        "### Metrics (`estimate_costs`, `compare` `by`)",
        "",
        "`compute_kpis` has names of its own, gemini's totals and the report of one result: call "
        "it without `names` and use the names it returns; costs come from `estimate_costs`.",
        "A study (`sample_uncertainty`, `sensitivity`, `run_study`) reads only the objectives "
        f"below and {', '.join(f'`{name}`' for name in STUDY_KPIS)}: never `capex` or `opex`.",
        "",
    ]
    for item in metrics():
        aim = "; an objective a study may minimise" if item["objective"] else ""
        lines.append(f"- `{item['name']}`: {item['title']}, in {item['unit']}{aim}")
    return "\n".join(lines)


def economics_text():
    """Return the economics keys with their units and meanings, from gemini's schema."""
    from geomind.tools.gemini.skeleton import keys_under

    lines = ['### Economics keys (the case\'s economics file; `read_case(section="economics")`)']
    return "\n".join([*lines, "", *keys_under("economics")])


def analysis_reference():
    """Return the whole gemini part of an analysis prompt."""
    return "\n\n".join([HEADING, metrics_text(), economics_text()])


def economist_appendix():
    """Return the economist's appendix: the analysis reference and the study keys."""
    from geomind.tools.gemini.skeleton import trees

    return f"{analysis_reference()}\n\n{trees('study')()}"

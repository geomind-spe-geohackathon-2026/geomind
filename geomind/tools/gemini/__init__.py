"""The tools over gemini: modules, plants, the brief, runs, results and their assessment.

Every tool uses only ``import gemini as gm``, inside its function, so ``import geomind`` stays free
of gemini. The catalogue, with the phase of every stub, is in ``tools.md``.
"""

from geomind.tools.gemini.assessment import (
    check_results,
    compute_kpis,
    estimate_costs,
    optimize,
    sample_uncertainty,
    test_module,
)
from geomind.tools.gemini.brief import set_brief
from geomind.tools.gemini.catalogue import describe_module, evaluate_module, list_modules
from geomind.tools.gemini.plants import build_plant, list_plants, read_plant
from geomind.tools.gemini.results import read_result, search_documents
from geomind.tools.gemini.runs import list_profiles, read_profile, simulate

__all__ = [
    "build_plant",
    "check_results",
    "compute_kpis",
    "describe_module",
    "estimate_costs",
    "evaluate_module",
    "list_modules",
    "list_plants",
    "list_profiles",
    "optimize",
    "read_plant",
    "read_profile",
    "read_result",
    "sample_uncertainty",
    "search_documents",
    "set_brief",
    "simulate",
    "test_module",
]

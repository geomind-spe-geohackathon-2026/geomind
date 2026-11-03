"""The tools over gemini: modules, plants, the case, runs, results and their assessment.

Every tool uses only ``import gemini as gm``, inside its function, so ``import geomind`` stays free
of gemini. The catalogue, with the phase of every stub, is in ``tools.md``.
"""

from geomind.tools.gemini.assessment import (
    check_results,
    compute_kpis,
    estimate_costs,
)
from geomind.tools.gemini.case import read_case, save_profile, set_case
from geomind.tools.gemini.catalogue import describe_module, evaluate_module, list_modules
from geomind.tools.gemini.origin import accept_case, case_changes
from geomind.tools.gemini.plants import (
    build_plant,
    list_plants,
    merge_designs,
    patch_plant,
    read_plant,
    set_ranges,
)
from geomind.tools.gemini.results import rag_search, read_result
from geomind.tools.gemini.runs import list_profiles, read_profile, simulate
from geomind.tools.gemini.studies import list_studies, read_study
from geomind.tools.gemini.study import (
    compare,
    evolve_structure,
    optimize,
    run_study,
    sample_uncertainty,
    sensitivity,
    size_plant,
)

__all__ = [
    "accept_case",
    "build_plant",
    "patch_plant",
    "case_changes",
    "check_results",
    "compare",
    "compute_kpis",
    "describe_module",
    "estimate_costs",
    "evaluate_module",
    "evolve_structure",
    "list_modules",
    "list_plants",
    "list_profiles",
    "list_studies",
    "merge_designs",
    "optimize",
    "read_case",
    "read_plant",
    "read_profile",
    "read_result",
    "read_study",
    "run_study",
    "sample_uncertainty",
    "save_profile",
    "rag_search",
    "sensitivity",
    "set_case",
    "set_ranges",
    "simulate",
    "size_plant",
]

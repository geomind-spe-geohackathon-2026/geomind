"""The skeleton of the explainer."""

from geomind.agents import Explainer
from tests.unit.agents.structure import check_skeleton


def test_the_skeleton_is_complete():
    """It constructs, its prompt has the six headings and its sections are in order."""
    check_skeleton(Explainer, "explainer")

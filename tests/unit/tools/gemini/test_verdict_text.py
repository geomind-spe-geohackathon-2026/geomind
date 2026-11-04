"""gemini's verdict and metrics as prompt text, read from gemini when the prompt renders."""

from geomind.tools.gemini.verdict_text import (
    metric_names,
    metrics_reference,
    reason_kinds,
    reviewer_reference,
    verdict_reference,
)


def test_the_reason_kinds_are_read_from_gemini_s_verdict():
    """Each kind has its meaning; a kind gemini adds or renames changes this set."""
    kinds = reason_kinds()
    assert set(kinds) == {"requirement", "failed_step", "numerical", "bound"}
    assert "residual" in kinds["numerical"]


def test_the_texts_name_each_kind_and_each_metric_once():
    """The verdict lists the kinds, the metrics every name of ``gm.evaluate.metrics``."""
    verdict = verdict_reference()
    assert all(f"- `{kind}`:" in verdict for kind in reason_kinds()) and "``" not in verdict
    metrics = metrics_reference()
    assert all(f"- `{name}`:" in metrics for name in metric_names())
    assert reviewer_reference() == f"{verdict}\n\n{metrics}"

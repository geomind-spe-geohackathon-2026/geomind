"""Prompt text from gemini's own verdict and metrics, for the reviewer and the explainer.

Made when a prompt renders, so the kinds of a verdict's reasons and the names of the metrics a
prompt shows are always gemini's: a kind or a metric gemini renames changes the prompt, and a
test fails when one a prompt names is gone.
"""

import inspect
import re

REASON_KIND = re.compile(r"^\s*- ``(\w+)``: (.*)")


def reason_kinds():
    """Return ``{kind: meaning}`` of a verdict's reasons, from ``gm.evaluate.verdict``'s doc."""
    import gemini as gm

    text = inspect.getdoc(gm.evaluate.verdict) or ""
    body = text.split("A reason has a ``kind``:", 1)[-1].split("The case is applied", 1)[0]
    kinds, current = {}, None
    for line in body.splitlines():
        match = REASON_KIND.match(line)
        if match:
            current = match[1]
            kinds[current] = match[2].strip()
        elif current and line.strip():
            kinds[current] += " " + line.strip()
    return kinds


def verdict_reference():
    """Return the prompt text of gemini's verdict: what each kind of reason means, its shape."""
    lines = ["## gemini's verdict", ""]
    lines.append(
        "`check_results` returns gemini's `feasible` (true only when there is no reason) and its "
        "`reasons`, each `{kind, name, message}` with `path`, `value`, `limit` and `worst_step` "
        "when it has them. The kinds:"
    )
    lines += [
        f"- `{kind}`: {meaning.replace('``', '`')}" for kind, meaning in reason_kinds().items()
    ]
    lines.append(
        "`failures` groups the failed and skipped rows of the run by module path and error code: "
        "each `{path, code, kind, count, first, last, message}`, `kind` `failed` or `skipped`, "
        "largest first (`gm.evaluate.failures`)."
    )
    return "\n".join(lines)


def metrics_reference():
    """Return the prompt text of gemini's metrics: name, title, display unit, objective or not."""
    import gemini as gm

    lines = ["## gemini's metrics", ""]
    from geomind.tools.gemini.assessment import COSTS

    lines.append(
        "gemini's metrics, in their display units; show each with the unit gemini gives, never "
        "converted. An objective is a metric a study can minimise. Call `compute_kpis(reference)` "
        "without `names`: it gives every total and report metric it has, and a name it has not "
        f"is an error. The costs ({', '.join(f'`{name}`' for name in COSTS)}) come from "
        "`estimate_costs`."
    )
    for metric in gm.evaluate.metrics():
        mark = ", objective" if metric["objective"] else ""
        lines.append(f"- `{metric['name']}`: {metric['title']}, in {metric['unit']}{mark}")
    return "\n".join(lines)


def metric_names():
    """Return the names of gemini's metrics."""
    import gemini as gm

    return {metric["name"] for metric in gm.evaluate.metrics()}


def reviewer_reference():
    """Return the reviewer's gemini part: the verdict, then the metrics."""
    return f"{verdict_reference()}\n\n{metrics_reference()}"

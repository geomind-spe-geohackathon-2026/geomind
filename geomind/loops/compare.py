"""Compare alternative plant families in one study and rank them."""

from geomind.loops.design import DesignDriver, DesignLoop, project_files_text, request_of


class CompareDriver(DesignDriver):
    """Drive a design whose designer compares two or three families with one ``run_study``."""

    def first_task(self, context):
        """Return the designer's first task: the request, and the comparison it must run."""
        return (
            f"{request_of(context)}{project_files_text(context)}\n\n"
            f"Round 1 of at most {self._max_rounds}. Read the case, then "
            "build and size two or three materially different families that gemini can run, "
            "compare them with one run_study (method minimize, prepare size), simulate the best "
            "feasible design for the whole year and check it. Record design.start_result, "
            "design.alternatives, design.study, design.reference and design.result."
        )


class CompareLoop(DesignLoop):
    """Design by comparing alternative families: the ranked table goes to the answer.

    It is a ``DesignLoop`` whose designer is asked for two or three families and compares them
    with one ``run_study``; the study is recorded in the state as ``design.study`` and the
    explainer's task carries its table. The verifier, the economist and the explainer, the rounds
    and the stops are the design loop's.
    """

    name = "compare"
    driver = CompareDriver

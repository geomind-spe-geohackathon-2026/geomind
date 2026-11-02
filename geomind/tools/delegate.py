"""A tool that runs another agent in a nested run."""

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import Tool
from geomind.types import Record
from geomind.utils.strings import first_paragraph

CHARACTERS_PER_TOKEN = 4


class DelegateInput(Record):
    """What the model passes: the task text."""

    task: str


class Delegate(Tool):
    """Run ``agent`` in a nested engine run with a clean context: the task text only.

    The nested run has its own run id, its own sandbox and ``parent`` set on every event. The model
    reads only the answer, cut to ``max_summary_tokens``. NOTE: the effect is ``compute`` so that
    delegating needs no approval of its own, because the nested tools are decided one by one. It is
    still not pure: a nested run neither runs beside others nor runs again in a replay, and after a
    crash it is not repeated.
    """

    def __init__(self, agent, max_summary_tokens=None):
        """Offer ``agent`` as a tool named after it."""
        super().__init__(
            agent.name,
            first_paragraph(type(agent).__doc__ or agent.name),
            DelegateInput.model_json_schema(),
            self._delegate,
            effect="compute",
            idempotent=False,
            input_model=DelegateInput,
        )
        self.agent = agent
        self.max_summary_tokens = max_summary_tokens

    @property
    def is_pure(self):
        """Return that a nested run is never pure."""
        return False

    async def _delegate(self, context, task):
        """Run the nested agent through the run of ``context``."""
        result = await context.session.delegate(self.agent, task)
        return self.outcome(result, context.session.child_limit)

    def outcome(self, result, limit=None):
        """Return the output of a finished nested run, or its request when it waits.

        ``limit`` is the reason a budget or time limit stopped the nested run: the error then has
        the code ``budget`` and names the limit with what was spent and the cap.
        """
        if result.request is not None:
            return result.request
        if result.status != "done" and limit is not None:
            raise ToolError(f"{self.name}: run {limit}", code="budget")
        if result.status != "done":
            raise ToolError(
                f"{self.name}: the nested run stopped with {result.stop_reason}", code="internal"
            )
        tokens = self.max_summary_tokens or runtime.get("delegate_summary_tokens")
        return str(result.answer)[: tokens * CHARACTERS_PER_TOKEN]

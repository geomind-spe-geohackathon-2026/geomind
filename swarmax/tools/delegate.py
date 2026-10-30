"""A tool that runs another agent in a nested run."""

from swarmax.core import runtime
from swarmax.core.types import Record
from swarmax.errors import ToolError
from swarmax.tools.base import Tool
from swarmax.utils.strings import first_paragraph

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

    async def _delegate(self, task):
        """Run the nested agent through the active run."""
        return self.outcome(await runtime.active_run().delegate(self.agent, task))

    def outcome(self, result):
        """Return the output of a finished nested run, or its request when it waits."""
        if result.request is not None:
            return result.request
        if result.status != "done":
            raise ToolError(f"{self.name}: {result.stop_reason}: {result.answer}")
        tokens = self.max_summary_tokens or runtime.get("delegate_summary_tokens")
        return str(result.answer)[: tokens * CHARACTERS_PER_TOKEN]

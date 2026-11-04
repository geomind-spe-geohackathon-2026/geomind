"""Replace older turns by one summary when the rendered context grows too long."""

from geomind.agents import Summarizer
from geomind.context.compaction import is_over_threshold, older_turns, transcript
from geomind.types import Message


async def compact_history(session, agent):
    """Summarize older turns before an LLM call that would pass the threshold.

    The check reads this run's own conversation only: its rendered messages and the input of its
    own last call, never what nested runs used, so each agent compacts on its own context.

    The summary is one ``compaction`` event, and ``apply`` makes the replacement, so a recovered run
    holds it and never summarizes twice. NOTE: with nothing old enough to replace the run goes on,
    because a turn that is still open must stay whole.
    """
    state = session.state
    rendered = session.context().messages_for(agent)
    if not is_over_threshold(rendered, agent.model.resolved_name(), state.last_input_tokens):
        return
    turns = older_turns(state.messages)
    if not turns:
        return
    summarizer = Summarizer()
    request = (
        Message(role="system", content=summarizer.prompt.render()),
        Message(role="user", content=transcript(state.messages, turns)),
    )
    await session.summarize(summarizer, request, len(turns))

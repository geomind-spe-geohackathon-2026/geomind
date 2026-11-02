"""A long chat stays under its threshold and remembers what it compacted."""

from geomind import runtime
from geomind.agents import Assistant
from geomind.context.compaction import estimate_tokens
from geomind.engine import Permissions
from geomind.run import Run
from geomind.stores import MemoryRunStore
from geomind.types import Completion, Message
from tests.fixtures.runs import of_type

TURNS = 50
FACT_TURN = 3
FACT = "The well on the north site is 2345 m deep."
TURN_CHARACTERS = 2000
LIMIT = 15_500
SHARE = LIMIT / 128_000


class Remembering:
    """A model that knows only what its messages hold, and a summarizer that keeps every fact."""

    def __init__(self):
        """Count the calls and the largest context."""
        self.summaries = 0
        self.largest = 0

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Answer from the messages, as a model with no other memory would."""
        text = " ".join(message.content for message in messages)
        if model == runtime.get("summarizer_model"):
            self.summaries += 1
            return Completion(text=FACT if FACT in text else "nothing", model=model)
        self.largest = max(self.largest, estimate_tokens(messages))
        return Completion(text=_answer(text), model=model)


def _answer(text):
    """Return the depth when the messages hold it, and a long plain answer otherwise."""
    if "How deep is the north well?" not in text:
        return "a" * (TURN_CHARACTERS // 2)
    return "2345 m" if "2345 m" in text else "I do not know."


def question(number):
    """Return the message of one turn."""
    if number == FACT_TURN:
        return FACT
    if number == TURNS:
        return "How deep is the north well?"
    return f"{number} " + "q" * (TURN_CHARACTERS // 2)


def take_turn(store, llm, number):
    """Answer one message of the chat and keep it in the history."""
    message = question(number)
    run = Run(
        message,
        chat="long",
        history=store.load_history("long"),
        llm=llm,
        store=store,
        permissions=Permissions("auto"),
        agent=Assistant(),
    )
    result = run.start()
    store.add_message("long", Message(role="user", content=message))
    store.add_message("long", Message(role="assistant", content=result.answer))
    return result


def test_a_fifty_turn_chat_compacts_once_and_keeps_the_answer():
    """Under the threshold throughout, one summary, and turn 3 is still known at turn 50."""
    store = MemoryRunStore()
    llm = Remembering()
    with runtime.settings(compaction_threshold=SHARE):
        results = [take_turn(store, llm, number) for number in range(1, TURNS + 1)]
    compacted = [
        number
        for number, result in enumerate(results, 1)
        if of_type(store.load_events(result.run_id), "compaction")
    ]
    assert llm.summaries == 1
    assert compacted == [32]
    assert llm.largest <= LIMIT
    assert results[-1].answer == "2345 m"
    assert store.load_state("long")["compaction"]["turns"] == 26


def test_the_summary_keeps_its_place_across_runs():
    """A later run reads the summary, not the turns it replaced."""
    store = MemoryRunStore()
    llm = Remembering()
    with runtime.settings(compaction_threshold=SHARE):
        for number in range(1, 34):
            take_turn(store, llm, number)
    started = of_type(store.load_events(next(reversed(store.events))), "run.started")[0]
    contents = [message.content for message in started.messages]
    assert contents[0].endswith(FACT)
    assert not any(content.startswith("10 q") for content in contents)

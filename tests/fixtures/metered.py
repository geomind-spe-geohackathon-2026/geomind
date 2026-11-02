"""A scripted provider with prices, so a budget can be tested against a small cap."""

from geomind.types import Completion, Usage

INPUT_PRICE = 3e-6
OUTPUT_PRICE = 15e-6
PRICES = {"fake/model": (INPUT_PRICE, OUTPUT_PRICE)}
WANTED_OUTPUT = 1000


class Metered:
    """Return scripted completions; bill them by tokens at the prices, and keep the settings.

    The output is the tokens the script wants, cut at the ``max_tokens`` of the call; the input is
    four characters per token of what was sent.
    """

    def __init__(self, completions):
        """Keep the script and an empty list of the settings received."""
        self.completions = list(completions)
        self.settings = []
        self.calls = 0

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Return the next completion with its usage computed from the call."""
        self.settings.append(settings)
        completion = self.completions[self.calls]
        self.calls += 1
        sent = sum(len(message.model_dump_json()) for message in messages) + len(str(tools))
        output = min(settings.get("max_tokens") or WANTED_OUTPUT, WANTED_OUTPUT)
        cost = (sent // 4) * INPUT_PRICE + output * OUTPUT_PRICE
        usage = Usage(input_tokens=sent // 4, output_tokens=output, cost=cost)
        return Completion(
            text=completion.text, tool_calls=completion.tool_calls, usage=usage, model=model
        )

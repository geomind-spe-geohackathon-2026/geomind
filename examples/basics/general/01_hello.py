"""The smallest run: one message, one answer; the coordinator routes it first."""

import geomind as gd
from examples.support import provider
from geomind.types import Completion, Usage

ROUTE = '{"kind": "loop", "loop": "tool", "agent": "analyst"}'
SCRIPT = [
    Completion(text=ROUTE, model="fake/cheap"),
    Completion(
        text="Hello! I have ask_user and finish.",
        usage=Usage(input_tokens=40, output_tokens=9),
        model="fake/model",
    ),
]


def main():
    """Run and print the answer."""
    result = gd.Run(message="Say hello and list the tools you have", llm=provider(SCRIPT)).start()
    print(result.answer)
    print(result.usage)


if __name__ == "__main__":
    main()

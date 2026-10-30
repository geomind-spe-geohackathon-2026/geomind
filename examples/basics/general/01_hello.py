"""The smallest run: one message, one answer."""

import geomind as gd
from examples.support import provider
from geomind.types import Completion, Usage

SCRIPT = [
    Completion(
        text="Hello! I have ask_user and finish.",
        usage=Usage(input_tokens=40, output_tokens=9),
        model="fake/model",
    )
]


def main():
    """Run and print the answer."""
    result = gd.Run(message="Say hello and list the tools you have", llm=provider(SCRIPT)).start()
    print(result.answer)
    print(result.usage)


if __name__ == "__main__":
    main()

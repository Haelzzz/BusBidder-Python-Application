"""Helpers shared by several test modules."""

from busbidder.console import Console


def scripted(*answers: str) -> tuple[Console, list[str]]:
    """A console that answers with ``answers`` in order and records prompts and output.

    Running out of answers raises ``EOFError``, like pressing Ctrl+D in a terminal.
    """
    output: list[str] = []
    supply = iter(answers)

    def answer(prompt: str) -> str:
        output.append(prompt)
        try:
            return next(supply)
        except StopIteration:
            raise EOFError from None

    return Console(answer, output.append), output

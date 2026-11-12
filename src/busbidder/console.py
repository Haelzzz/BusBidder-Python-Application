"""Asking the user questions in the terminal.

Every question re-asks until the answer is valid. Brackets show either the
expected format (``[YYYY-MM-DD]``) or a suggested value that pressing Enter
accepts (``[2026-07-19]``, ``[default: 1]``). Optional questions say so and
return ``None`` on Enter. All input and output goes through one ``Console``
object, so tests can run a whole session with scripted answers.
"""

import math
from collections.abc import Callable, Sequence
from datetime import date, datetime, time

from busbidder.patterns import TIME_RE

OPTIONAL = "(optional, press Enter to skip)"


class Console:
    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self._input = input_fn
        self._output = output_fn

    def say(self, text: str = "") -> None:
        self._output(text)

    def ask(self, prompt: str) -> str:
        return self._input(prompt).strip()

    def choose(self, title: str, options: Sequence[str], *, allow_back: bool = True) -> int | None:
        """Show numbered options and return the chosen index, or ``None`` if the user goes back."""
        self.say(title)
        for number, option in enumerate(options, start=1):
            self.say(f"  {number:>2}) {option}")
        hint = " (Enter to go back)" if allow_back else ""
        while True:
            answer = self.ask(f"Choose 1-{len(options)}{hint}: ")
            if not answer and allow_back:
                return None
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1
            self.say(f"Please enter a number from 1 to {len(options)}.")

    def ask_date(self, prompt: str, default: date | None = None, *, optional: bool = False) -> date | None:
        """A date typed as YYYY-MM-DD. Enter gives ``default``, or ``None`` if ``optional``."""
        shown = "YYYY-MM-DD" if default is None else str(default)
        while True:
            answer = self.ask(f"{prompt} [{shown}]: ")
            if not answer:
                if default is not None:
                    return default
                if optional:
                    return None
            else:
                try:
                    return datetime.strptime(answer, "%Y-%m-%d").date()
                except ValueError:
                    pass
            self.say("Please enter a date as YYYY-MM-DD, e.g. 2026-07-12.")

    def ask_time(self, prompt: str) -> time:
        """A clock time typed as HH:MM."""
        while True:
            match = TIME_RE.fullmatch(self.ask(f"{prompt} [HH:MM]: "))
            if match:
                return time(int(match["hour"]), int(match["minute"]))
            self.say("Please enter a time as HH:MM, e.g. 09:30.")

    def ask_int(self, prompt: str, default: int | None, minimum: int, maximum: int | None = None) -> int | None:
        """A whole number in [minimum, maximum]; Enter gives ``default`` (``None`` = optional)."""
        suffix = OPTIONAL if default is None else f"[default: {default}]"
        while True:
            answer = self.ask(f"{prompt} {suffix}: ")
            if not answer:
                return default
            if answer.lstrip("-").isdigit():
                value = int(answer)
                if value >= minimum and (maximum is None or value <= maximum):
                    return value
            limit = f"from {minimum} to {maximum}" if maximum is not None else f"of at least {minimum}"
            self.say(f"Please enter a whole number {limit}.")

    def ask_float(self, prompt: str, default: float | None, minimum: float) -> float | None:
        """A number of at least ``minimum``; Enter gives ``default`` (``None`` = optional)."""
        suffix = OPTIONAL if default is None else f"[default: {default:g}]"
        while True:
            answer = self.ask(f"{prompt} {suffix}: ")
            if not answer:
                return default
            try:
                value = float(answer.replace(",", "."))  # accept 49,50 as well as 49.50
            except ValueError:
                value = None
            if value is not None and math.isfinite(value) and value >= minimum:  # "nan" and "inf" parse too
                return value
            self.say(f"Please enter a number of at least {minimum:g}.")

    def confirm(self, prompt: str, default: bool = False) -> bool:
        options = "Y/n" if default else "y/N"
        while True:
            answer = self.ask(f"{prompt} [{options}]: ").lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self.say("Please answer y or n.")

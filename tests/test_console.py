"""Tests for the terminal prompt helpers, using scripted answers."""

from datetime import date, time

import pytest
from helpers import scripted


def test_choose_returns_index() -> None:
    console, _ = scripted("2")
    assert console.choose("Pick:", ["a", "b", "c"]) == 1


def test_choose_repeats_until_valid() -> None:
    console, output = scripted("0", "4", "x", "3")
    assert console.choose("Pick:", ["a", "b", "c"]) == 2
    assert output.count("Please enter a number from 1 to 3.") == 3


def test_choose_enter_goes_back_only_when_allowed() -> None:
    console, _ = scripted("")
    assert console.choose("Pick:", ["a"]) is None
    console, _ = scripted("", "1")
    assert console.choose("Pick:", ["a"], allow_back=False) == 0


def test_ask_date() -> None:
    console, output = scripted("", "12/07/2026", "2026-06-31", "2026-07-14")
    assert console.ask_date("From", date(2026, 7, 8)) == date(2026, 7, 8)  # Enter = default
    assert console.ask_date("To", date(2026, 7, 8)) == date(2026, 7, 14)
    assert output.count("Please enter a date as YYYY-MM-DD, e.g. 2026-07-12.") == 2


def test_date_without_default_shows_the_format_and_requires_an_answer() -> None:
    console, output = scripted("", "2026-07-12")
    assert console.ask_date("When?") == date(2026, 7, 12)
    assert output[0] == "When? [YYYY-MM-DD]: "
    assert "Please enter a date as YYYY-MM-DD, e.g. 2026-07-12." in output


def test_optional_date_may_be_skipped() -> None:
    console, _ = scripted("")
    assert console.ask_date("Latest?", optional=True) is None


def test_ask_time() -> None:
    console, output = scripted("9:30", "24:00", "09:30")
    assert console.ask_time("Leave at?") == time(9, 30)
    assert output[0] == "Leave at? [HH:MM]: "
    assert output.count("Please enter a time as HH:MM, e.g. 09:30.") == 2


def test_prompts_show_default_or_optional() -> None:
    console, output = scripted("", "")
    console.ask_int("Seats?", default=1, minimum=1)
    console.ask_float("Budget?", default=None, minimum=0)
    assert output == ["Seats? [default: 1]: ", "Budget? (optional, press Enter to skip): "]


@pytest.mark.parametrize("answers, expected", [
    ([""], 1),  # default
    (["3"], 3),
    (["10"], 10),  # maximum is allowed
    (["0", "11", "2.5", "-1", "abc", "4"], 4),
])
def test_ask_int_bounds(answers: list[str], expected: int) -> None:
    console, _ = scripted(*answers)
    assert console.ask_int("Seats", default=1, minimum=1, maximum=10) == expected


def test_ask_int_without_default_can_be_left_empty() -> None:
    console, _ = scripted("")
    assert console.ask_int("Optional", default=None, minimum=0) is None


@pytest.mark.parametrize("answers, expected", [
    ([""], None),
    (["49.50"], 49.5),
    (["49,50"], 49.5),  # decimal comma
    (["0"], 0.0),  # minimum is allowed
    (["-5", "nan", "inf", "cheap", "30"], 30.0),
])
def test_ask_float(answers: list[str], expected: float | None) -> None:
    console, _ = scripted(*answers)
    assert console.ask_float("Budget", default=None, minimum=0) == expected


@pytest.mark.parametrize("answers, default, expected", [
    ([""], False, False),
    ([""], True, True),
    (["y"], False, True),
    (["YES"], False, True),
    (["no"], True, False),
    (["maybe", "n"], True, False),
])
def test_confirm(answers: list[str], default: bool, expected: bool) -> None:
    console, _ = scripted(*answers)
    assert console.confirm("Sure?", default=default) is expected


def test_running_out_of_input_raises_eof() -> None:
    console, _ = scripted()
    with pytest.raises(EOFError):
        console.ask("Anything? ")

"""End-to-end tests of the command-line interface with scripted answers.

The sessions run on the real data, but bookings and the review file go to a
temporary folder.
"""

import dataclasses
import json
import re
from pathlib import Path

import pytest
from helpers import scripted

from busbidder.cli import App, main, run
from busbidder.settings import load_settings

# Menu: 1 search, 2 compare, 3 view bookings, 4 quit.
# Search answers: destination 7 = Malaga (alphabetical), first and last date, seats (Enter = 1),
# budget, max hours (Enter = none), profile 1 = balanced (the specification example).
MALAGA_SEARCH = ["1", "7", "2026-07-12", "2026-07-14", "", "50", "", "1"]


@pytest.fixture
def app(tmp_path: Path) -> App:
    settings = dataclasses.replace(load_settings(), review_file=tmp_path / "rejected.csv",
                                   bookings_file=tmp_path / "bookings.json")
    return App.start(settings)


def session(app: App, *answers: str) -> str:
    console, output = scripted(*answers)
    assert run(app, console) == 0
    return "\n".join(output)


# --- Search and book -------------------------------------------------------------

def test_search_rank_and_book(app: App) -> None:
    offer = app.repository.find_offer("OF-SOL-MAL-0011")
    seats_before = offer.available_seats

    output = session(app, *MALAGA_SEARCH, "1", "Test Person", "y", "3", "4")

    assert "Madrid -> Malaga, 12 Jul - 14 Jul, 1 seat - Balanced traveller" in output
    assert "Must have:   at least 1 seat(s) available; total price at most EUR 50.00" in output
    assert ("Priorities (most important first): low price, short journey, "
            "flexible ticket (change or refund), departure close to 09:00") in output
    assert "15 of 102 offers fit your trip (not shown: other dates 75, over budget 26" in output
    assert re.search(r"1\.  SolRuta\s+Mon 13 Jul  12:15 .* <- recommended", output)
    assert "Why we recommend no. 1:" in output
    reference = re.search(r"Booking confirmed: (BB-\w{6})", output).group(1)
    assert offer.available_seats == seats_before - 1
    saved = json.loads(app.settings.bookings_file.read_text(encoding="utf-8"))
    assert [b["reference"] for b in saved] == [reference]
    assert re.search(rf"{reference}\s+\S+ \S+\s+Test Person\s+OF-SOL-MAL-0011", output)  # bookings list
    assert output.endswith("Goodbye.")


def test_simple_view_hides_scores_per_criterion(app: App) -> None:
    output = session(app, *MALAGA_SEARCH, "", "4")
    assert "Weights:" not in output
    assert "OF-SOL-MAL-0011" not in output  # offer IDs only in the details view
    assert "travel_window" not in output


def test_details_view_shows_scores_weights_and_full_explanation(app: App) -> None:
    output = session(app, *MALAGA_SEARCH, "d", "", "4")
    assert "Score details" in output
    assert "Weights: price 40%, duration 25%, departure 15%, flexibility 20%" in output
    assert "31.00 (98)" in output  # raw value and criterion score
    assert "Compared with #2" in output
    assert "not objectively the best offer" in output


def test_all_shows_the_rest_of_the_list(app: App) -> None:
    output = session(app, *MALAGA_SEARCH, "all", "", "4")
    assert "... and 5 more (enter 'all' to see them)" in output
    assert re.search(r"\n\s+15\.  ", output)


def test_invalid_choice_is_asked_again(app: App) -> None:
    output = session(app, *MALAGA_SEARCH, "99", "", "4")
    assert "Please enter a number from 1 to 15, 'd', or press Enter." in output


def test_declining_the_confirmation_books_nothing(app: App) -> None:
    output = session(app, *MALAGA_SEARCH, "1", "Test Person", "n", "4")
    assert "Not booked; nothing was saved." in output
    assert not app.settings.bookings_file.exists()


def test_several_seats_show_price_per_seat_and_total(app: App) -> None:
    search = MALAGA_SEARCH.copy()
    search[4], search[5] = "2", ""  # 2 seats, no budget
    output = session(app, *search, "1", "Ana", "n", "4")
    assert "2 seats" in output and "Prices are per seat." in output
    assert re.search(r"2 seat\(s\) x EUR \d+\.\d\d = EUR \d+\.\d\d", output)


def test_no_acceptable_offer_returns_to_menu(app: App) -> None:
    search = MALAGA_SEARCH.copy()
    search[5] = "5"  # budget EUR 5
    output = session(app, *search, "4")
    assert "No offer fits all your requirements." in output


# --- Dates --------------------------------------------------------------------------

def test_date_prompts_show_the_format_and_range(app: App) -> None:
    output = session(app, *MALAGA_SEARCH, "", "4")
    assert "Buses run from 8 to 19 July 2026." in output
    assert "When do you want to travel? [YYYY-MM-DD]: " in output
    assert "How many seats? [default: 1]: " in output
    assert "Maximum total price in EUR (optional, press Enter to skip): " in output


def test_date_without_buses_suggests_the_closest(app: App) -> None:
    output = session(app, "1", "7", "2026-08-01", "", "", "", "", "", "1", "", "4")
    assert "There are no buses to Malaga on 2026-08-01. Closest date with departures [2026-07-19]: " in output
    assert "Madrid -> Malaga, Sun 19 Jul, 1 seat" in output  # Enter on the latest date = only that day


def test_end_date_before_start_is_asked_again(app: App) -> None:
    output = session(app, "1", "7", "2026-07-14", "2026-07-12", "2026-07-14", "", "", "", "")
    assert "The latest date cannot be before 2026-07-14." in output


# --- Own priorities -------------------------------------------------------------------

def test_own_priorities_become_weights(app: App) -> None:
    # Importance: price 3, duration 1, departure 2, flexibility 0, emissions 0; then the time.
    priorities = MALAGA_SEARCH[:-1] + ["6", "3", "1", "2", "0", "0", "25:00", "09:30"]
    output = session(app, *priorities, "d", "", "4")
    assert "Please enter a time as HH:MM" in output
    assert ("Your priorities: low price 50%, departure close to your preferred time 33%, "
            "short journey 17% (leaving around 09:30)") in output
    assert "Weights: price 50%, duration 17%, departure 33%" in output  # details view


def test_own_priorities_need_at_least_one_above_zero(app: App) -> None:
    # All 0 first; then price 1, duration Enter (default 1), departure 0, the rest Enter (default 0).
    priorities = MALAGA_SEARCH[:-1] + ["6", "0", "0", "0", "0", "0", "1", "", "0", "", ""]
    output = session(app, *priorities, "", "4")
    assert "Please give at least one of them an importance above 0." in output
    assert "Your priorities: low price 50%, short journey 50%" in output


# --- Other menu options -------------------------------------------------------------------

def test_compare_shows_summary_then_details_on_request(app: App) -> None:
    output = session(app, "2", "3", "", "4")
    assert "The same 102 offers, recommended for 5 kinds of traveller:" in output
    assert "Business traveller: Needs a direct, changeable trip" in output  # details of no. 3
    assert output.count("Hard constraints (an offer must meet all of them):") == 1


def test_going_back_and_viewing_empty_bookings(app: App) -> None:
    output = session(app, "1", "", "3", "4")
    assert "No bookings yet." in output


def test_end_of_input_quits_gracefully(app: App) -> None:
    assert session(app, "1").endswith("Goodbye.")


def test_compare_mode_prints_every_profile_in_full(capsys: pytest.CaptureFixture) -> None:
    assert main(["--compare"]) == 0
    output = capsys.readouterr().out
    assert "recommended for 5 kinds of traveller" in output
    assert output.count("Hard constraints (an offer must meet all of them):") == 5
    for name in ("Budget traveller", "Business traveller", "Flexibility-focused tourist"):
        assert name in output

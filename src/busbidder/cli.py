"""Command-line interface.

    python -m busbidder            interactive menu: search, rank and book
    python -m busbidder --compare  compare every traveller profile on the example trip, then exit

``main`` reads settings and loads everything; ``run`` is the session itself and
takes a ``Console``, so tests can drive it with scripted answers.

Results are shown in two views: a simple one for customers (plain words, one
total score per offer), and a details view on request with every criterion
score, the weights and the full explanation, as the specification requires.
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from busbidder.booking import BookingService, BookingStore, format_confirmation
from busbidder.booking.service import MAX_NAME_LENGTH
from busbidder.console import Console
from busbidder.data_io.loader import LoadReport, load_marketplace
from busbidder.data_io.profiles import load_profiles
from busbidder.data_io.repository import MarketplaceRepository
from busbidder.exceptions import BookingError, BusBidderError, ConfigError
from busbidder.filtering import FilterResult, filter_offers
from busbidder.logging_setup import setup_logging
from busbidder.models import FareConditions, Offer, TravellerProfile, TravellerRequest, Trip
from busbidder.paths import PROJECT_ROOT
from busbidder.ranking import SHORT_CAVEAT, Explanation, Ranking, explain_top, rank_offers, validate_weights
from busbidder.ranking.base import CRITERIA
from busbidder.settings import Settings, load_settings

logger = logging.getLogger(__name__)

# The trip from the specification, used by --compare and the compare menu option.
EXAMPLE_TRIP = Trip("MAL", date(2026, 7, 12), date(2026, 7, 14), max_budget_eur=50.0)
TOP_ROWS = 10
COMPARE_TOP_ROWS = 5
MAX_SEATS = 10
DIVIDER = "=" * 100
# Suggested answers for "Set my own priorities" (0 = not at all, 3 = very important).
DEFAULT_IMPORTANCE = {"price": 2, "duration": 1, "departure": 1, "flexibility": 0, "emissions": 0}


@dataclass
class App:
    """Everything a session needs, loaded once at start-up."""

    settings: Settings
    repository: MarketplaceRepository
    report: LoadReport
    profiles: dict[str, TravellerProfile]
    bookings: BookingService

    @classmethod
    def start(cls, settings: Settings) -> "App":
        repository, report = load_marketplace(settings)
        profiles = load_profiles()
        bookings = BookingService(repository, BookingStore(settings.bookings_file))
        return cls(settings, repository, report, profiles, bookings)


def main(argv: list[str] | None = None) -> int:
    """Run the application and return a process exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m busbidder",
        description="BusBidder Spain: filter, rank and book fictional bus offers from Madrid.",
    )
    parser.add_argument("--compare", action="store_true",
                        help="compare all traveller profiles on the example trip from the specification, then exit")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    setup_logging(settings.log_file, settings.log_level)
    logger.info("BusBidder started%s", " (--compare)" if args.compare else "")
    try:
        app = App.start(settings)
    except BusBidderError as exc:
        logger.error("Start-up failed: %s", exc)
        return 1
    return run(app, Console(), compare_only=args.compare)


def run(app: App, console: Console, *, compare_only: bool = False) -> int:
    console.say(app.report.summary())
    if app.report.rejected:
        console.say(f"Rejected records written to {_display(app.settings.review_file)} "
                    f"(details in {_display(app.settings.log_file)})")
    if app.bookings.bookings:
        console.say(f"{len(app.bookings.bookings)} saved booking(s) loaded from "
                    f"{_display(app.settings.bookings_file)}; seat counts updated.")
    if compare_only:
        compare_profiles(app, console, details=True)
        return 0
    try:
        main_menu(app, console)
    except (EOFError, KeyboardInterrupt):  # Ctrl+D / Ctrl+C
        console.say("\nGoodbye.")
    return 0


def main_menu(app: App, console: Console) -> None:
    actions = [
        ("Search and book a bus", search_and_book),
        ("See how different travellers would choose (example trip)", compare_profiles),
        ("View bookings", show_bookings),
    ]
    while True:
        console.say(f"\n{DIVIDER}\nBusBidder Spain")
        choice = console.choose("What would you like to do?", [label for label, _ in actions] + ["Quit"],
                                allow_back=False)
        if choice == len(actions):
            console.say("Goodbye.")
            return
        try:
            actions[choice][1](app, console)
        except BusBidderError as exc:
            logger.error("Action failed: %s", exc)
            console.say(f"Error: {exc}")


# --- Search and book ------------------------------------------------------------

def search_and_book(app: App, console: Console) -> None:
    console.say(f"\n{DIVIDER}\nNew search. Press Enter to accept a value shown in brackets.")
    trip = ask_trip(app, console)
    if trip is None:
        return
    profile = ask_profile(app, console)
    if profile is None:
        return
    request = profile.request_for(trip)
    result = filter_offers(app.repository.offers_to(trip.destination_id), request)
    ranking = rank_offers(result.accepted, request)

    show_results(app, console, profile, trip, result, ranking)
    if not ranking.offers:
        return
    chosen = ask_offer(console, result, ranking)
    if chosen is not None:
        book(app, console, chosen, trip.seats)


def ask_trip(app: App, console: Console) -> Trip | None:
    destinations = sorted(app.repository.destinations.values(), key=lambda d: d.name)
    index = console.choose("\nWhere do you want to go from Madrid?", [d.name for d in destinations])
    if index is None:
        return None
    destination = destinations[index]
    available = sorted({offer.travel_date for offer in app.repository.offers_to(destination.destination_id)})

    console.say(f"\nBuses run from {_date_span(available[0], available[-1])}.")
    earliest = ask_travel_date(console, "When do you want to travel?", destination.name, available)
    while True:
        latest = ask_travel_date(console, "Latest date you could travel, or press Enter for only that day",
                                 destination.name, available, optional=True)
        if latest is None:
            latest = earliest
        if latest >= earliest:
            break
        console.say(f"The latest date cannot be before {earliest}.")

    seats = console.ask_int("How many seats?", default=1, minimum=1, maximum=MAX_SEATS)
    budget = console.ask_float("Maximum total price in EUR", None, 0)
    hours = console.ask_float("Maximum journey time in hours", None, 0.5)
    return Trip(
        destination_id=destination.destination_id,
        earliest_date=earliest,
        latest_date=latest,
        seats=seats,
        max_budget_eur=budget,
        max_duration_min=None if hours is None else round(hours * 60),
    )


def ask_travel_date(
    console: Console, prompt: str, destination_name: str, available: list[date], *, optional: bool = False,
) -> date | None:
    """Ask for a date; if no bus runs that day, suggest the closest day that has departures."""
    day = console.ask_date(prompt, optional=optional)
    while day is not None and day not in available:
        closest = min(available, key=lambda d: (abs((d - day).days), d))  # earlier day wins a tie
        day = console.ask_date(f"There are no buses to {destination_name} on {day}. Closest date with departures",
                               default=closest)
    return day


def ask_profile(app: App, console: Console) -> TravellerProfile | None:
    profiles = list(app.profiles.values())
    options = [f"{p.name}: {p.description}" for p in profiles] + ["Set my own priorities"]
    index = console.choose("\nWhich kind of traveller are you?", options)
    if index is None:
        return None
    if index == len(profiles):
        return ask_own_priorities(console)
    return profiles[index]


def ask_own_priorities(console: Console) -> TravellerProfile:
    """Build a profile from importance levels 0-3, turned into weights by dividing by their sum."""
    console.say("\nHow important is each of these to you? (0 = not at all, 3 = very important)")
    while True:
        levels = {}
        for name in CRITERIA.names():
            label = CRITERIA.get(name).plain_label
            levels[name] = console.ask_int(f"  {_sentence(label)}", default=DEFAULT_IMPORTANCE.get(name, 1),
                                           minimum=0, maximum=3)
        if sum(levels.values()) > 0:
            break
        console.say("Please give at least one of them an importance above 0.")

    preferred = console.ask_time("What time would you like to leave?") if levels.get("departure") else None
    total = sum(levels.values())
    weights = validate_weights({name: level / total for name, level in levels.items() if level})
    profile = TravellerProfile(key="custom", name="Your own priorities", description="entered by you",
                               weights=weights, preferred_departure=preferred)
    shares = sorted(weights.items(), key=lambda item: -item[1])
    summary = ", ".join(f"{CRITERIA.get(name).plain_label} {weight:.0%}" for name, weight in shares)
    console.say(f"Your priorities: {summary}" + (f" (leaving around {preferred:%H:%M})" if preferred else ""))
    return profile


def show_results(
    app: App, console: Console, profile: TravellerProfile, trip: Trip, result: FilterResult, ranking: Ranking,
) -> None:
    """The simple view: requirements, priorities, offer list and a short recommendation."""
    request = result.request
    destination = app.repository.destinations[trip.destination_id].name
    seats = "1 seat" if trip.seats == 1 else f"{trip.seats} seats"
    console.say(f"\n{DIVIDER}\nMadrid -> {destination}, {_window(trip)}, {seats} - {profile.name}")
    must = [c.requirement(request) for c in result.constraints if c.name not in ("destination", "travel_window")]
    console.say(f"Must have:   {'; '.join(must)}")
    console.say(f"Priorities (most important first): {_priorities(request)}")

    total = len(result.accepted) + len(result.rejected)
    removed = result.removed_by()
    reasons = ", ".join(f"{c.plain_reason} {removed[c.name]}" for c in result.constraints if removed[c.name])
    console.say(f"{len(result.accepted)} of {total} offers fit your trip" + (f" (not shown: {reasons})" if reasons else ""))

    if not ranking.offers:
        console.say("\nNo offer fits all your requirements.")
        blocked = result.blocked_only_by()
        if blocked:
            name, count = blocked.most_common(1)[0]
            constraint = next(c for c in result.constraints if c.name == name)
            console.say(f"{count} offer(s) would fit if you relaxed: {constraint.requirement(request)}.")
        return

    console.say()
    console.say(offer_list(ranking, limit=TOP_ROWS, seats=trip.seats))
    console.say("\nWhy we recommend no. 1:")
    console.say(_plain_explanation(explain_top(ranking)))
    console.say(SHORT_CAVEAT)


def offer_list(ranking: Ranking, *, limit: int | None = None, seats: int = 1) -> str:
    """Numbered offers in ranked order, in plain columns, with one total score each."""
    lines = [f"{'No.':>5}  {'Company':<16}{'Date':<12}{'Departs':<9}{'Arrives':<10}{'Journey':<9}"
             f"{'Transfers':<11}{'Ticket':<12}{'Price':>8}{'Score':>7}"]
    shown = ranking.offers[:limit]
    for number, ranked in enumerate(shown, start=1):
        offer = ranked.offer
        arrives = f"{offer.arrival:%H:%M}" + (" +1" if offer.is_overnight else "")
        line = (f"{number:>4}.  {offer.company.name:<16}{offer.departure:%a %d %b}  {offer.departure:%H:%M}    "
                f"{arrives:<10}{_hours(offer.duration_min):<9}{offer.transfers:<11}{_ticket(offer.fare):<12}"
                f"{offer.price_eur:>8.2f}{ranked.total:>7.0f}")
        lines.append(line + ("  <- recommended" if number == 1 else ""))
    if len(shown) < len(ranking.offers):
        lines.append(f"       ... and {len(ranking.offers) - len(shown)} more (enter 'all' to see them)")
    if seats > 1:
        lines.append("Prices are per seat. Score: 0-100, higher is a better match for the priorities.")
    else:
        lines.append("Score: 0-100, higher is a better match for the priorities.")
    return "\n".join(lines)


def show_details(console: Console, result: FilterResult, ranking: Ranking) -> None:
    """The details view: hard constraints, every criterion score and weight, and the full explanation."""
    console.say(f"\n{DIVIDER}\nScore details\n")
    console.say(result.summary())
    console.say("\nRanking (raw value and score 0-100 per criterion; # is the rank, equal scores share a rank):")
    console.say(ranking.table())
    console.say()
    console.say(explain_top(ranking).text())


def ask_offer(console: Console, result: FilterResult, ranking: Ranking) -> Offer | None:
    """Let the user pick an offer by its number in the list, or open the details view."""
    count = len(ranking.offers)
    show_all = f", 'all' to see all {count}" if count > TOP_ROWS else ""
    while True:
        answer = console.ask(f"\nEnter a number to book{show_all}, 'd' for score details, "
                             "or press Enter to go back: ").lower()
        if not answer:
            return None
        if answer == "all":
            console.say(offer_list(ranking))
        elif answer == "d":
            show_details(console, result, ranking)
        elif answer.isdigit() and 1 <= int(answer) <= count:
            return ranking.offers[int(answer) - 1].offer
        else:
            console.say(f"Please enter a number from 1 to {count}, 'd', or press Enter.")


def book(app: App, console: Console, offer: Offer, seats: int) -> None:
    total = offer.price_eur * seats
    route = "direct" if offer.is_direct else f"{offer.transfers} transfer(s)"
    console.say(f"\n{offer.company.name}: Madrid -> {offer.destination.name}")
    console.say(f"  {offer.departure:%a %d %b %H:%M} -> {offer.arrival:%a %d %b %H:%M} "
                f"({_hours(offer.duration_min)}, {route})")
    console.say(f"  Ticket: {_ticket_long(offer.fare)}, {offer.fare.luggage_kg} kg luggage included")
    console.say(f"  {seats} seat(s) x EUR {offer.price_eur:.2f} = EUR {total:.2f} "
                f"({offer.available_seats} seat(s) left)")
    console.say("  Payment is simulated: no payment details are asked for.")

    while True:
        name = console.ask("Traveller name: ")
        if name and len(name) <= MAX_NAME_LENGTH:
            break
        console.say(f"Please enter a name of 1 to {MAX_NAME_LENGTH} characters.")
    if not console.confirm(f"Book {seats} seat(s) for EUR {total:.2f}?"):
        console.say("Not booked; nothing was saved.")
        return
    try:
        booking = app.bookings.book(offer.offer_id, name, seats)
    except BookingError as exc:
        console.say(f"Booking failed: {exc}")
        return
    console.say("\n" + format_confirmation(booking, offer))
    console.say(f"Saved to {_display(app.settings.bookings_file)}.")


def show_bookings(app: App, console: Console) -> None:
    bookings = app.bookings.bookings
    if not bookings:
        console.say("\nNo bookings yet.")
        return
    console.say(f"\n{'Reference':<11}{'Booked':<18}{'Traveller':<20}{'Offer':<17}{'Departs':<14}"
                f"{'Seats':>5}{'Total EUR':>11}  Status")
    for b in bookings:
        offer = app.repository.find_offer(b.offer_id)
        departs = f"{offer.departure:%d %b %H:%M}" if offer else "not in data"
        console.say(f"{b.reference:<11}{b.created_at:%Y-%m-%d %H:%M}  {b.traveller_name[:19]:<20}{b.offer_id:<17}"
                    f"{departs:<14}{b.seats:>5}{b.total_price_eur:>11.2f}  {b.status}")


# --- Profile comparison -------------------------------------------------------------

def compare_profiles(app: App, console: Console, trip: Trip = EXAMPLE_TRIP, *, details: bool = False) -> None:
    """Run every profile on the same trip, to show that the same offers give different recommendations.

    Shows a summary table first; ``details`` (used by --compare) prints every
    profile's full results as well, otherwise the user can open one at a time.
    """
    runs = []
    for profile in app.profiles.values():
        request = profile.request_for(trip)
        result = filter_offers(app.repository.offers_to(trip.destination_id), request)
        runs.append((profile, result, rank_offers(result.accepted, request)))

    if details:
        for run_ in runs:
            _profile_details(console, *run_)

    destination = app.repository.destinations[trip.destination_id].name
    budget = f", budget EUR {trip.max_budget_eur:.2f}" if trip.max_budget_eur is not None else ""
    offers = len(runs[0][1].accepted) + len(runs[0][1].rejected)
    console.say(f"\n{DIVIDER}\nExample trip: Madrid -> {destination}, {_window(trip)}{budget}")
    console.say(f"The same {offers} offers, recommended for {len(runs)} kinds of traveller:\n")
    console.say(f"{'No.':>5}  {'Traveller':<44}{'Fit':>4}  {'Recommended':<36}{'Price':>8}{'Score':>7}")
    for number, (profile, result, ranking) in enumerate(runs, start=1):
        top = ranking.top
        if top is None:
            console.say(f"{number:>4}.  {profile.name:<44}{0:>4}  no offer fits")
            continue
        offer = top.offer
        recommended = f"{offer.company.name}, {offer.departure:%a %d %b %H:%M}"
        console.say(f"{number:>4}.  {profile.name:<44}{len(result.accepted):>4}  {recommended:<36}"
                    f"{offer.price_eur:>8.2f}{top.total:>7.0f}")
        console.say(f"{'':7}{_reason_line(explain_top(ranking))}")
    console.say("\nFit = offers that meet the traveller's requirements. Score: 0-100 for that traveller's priorities.")
    if details:
        return

    while True:
        answer = console.ask("\nEnter a traveller number to see the details, or press Enter to go back: ")
        if not answer:
            return
        if answer.isdigit() and 1 <= int(answer) <= len(runs):
            _profile_details(console, *runs[int(answer) - 1])
        else:
            console.say(f"Please enter a number from 1 to {len(runs)}, or press Enter.")


def _profile_details(console: Console, profile: TravellerProfile, result: FilterResult, ranking: Ranking) -> None:
    console.say(f"\n{DIVIDER}\n{profile.name}: {profile.description}\n")
    console.say(result.summary())
    if ranking.offers:
        console.say(f"\nTop {min(COMPARE_TOP_ROWS, len(ranking.offers))} of {len(ranking.offers)} "
                    "(raw value and score 0-100 per criterion):")
        console.say(ranking.table(limit=COMPARE_TOP_ROWS))
        console.say()
        console.say(explain_top(ranking).text())


# --- Formatting helpers -------------------------------------------------------------

def _priorities(request: TravellerRequest) -> str:
    # sorted() is stable, so equal weights keep the profile's order.
    weighted = sorted(((w, n) for n, w in request.weights.items() if w > 0), key=lambda item: -item[0])
    return ", ".join(CRITERIA.create(name).plain_label_for(request) for _, name in weighted)


def _plain_explanation(explanation: Explanation) -> str:
    lines = [f"  + {_sentence(p.text)}" for p in explanation.advantages] or ["  + A good compromise across your priorities"]
    lines += [f"  - {_sentence(p.text)}" for p in explanation.disadvantages]
    return "\n".join(lines)


def _reason_line(explanation: Explanation) -> str:
    good = explanation.advantages[0].text if explanation.advantages else "a compromise across the priorities"
    line = f"+ {good}"
    if explanation.disadvantages:
        line += f"   - {explanation.disadvantages[0].text}"
    return line


def _ticket(fare: FareConditions) -> str:
    if fare.changeable and fare.refundable:
        return "refundable"
    return "changeable" if fare.changeable else "fixed"


def _ticket_long(fare: FareConditions) -> str:
    if fare.changeable and fare.refundable:
        return "changeable and refundable"
    return "changeable, not refundable" if fare.changeable else "fixed (cannot be changed or refunded)"


def _hours(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def _date_span(first: date, last: date) -> str:
    """E.g. "8 to 19 July 2026"."""
    if (first.year, first.month) == (last.year, last.month):
        return f"{first.day} to {last.day} {last:%B %Y}"
    if first.year == last.year:
        return f"{first.day} {first:%B} to {last.day} {last:%B %Y}"
    return f"{first.day} {first:%B %Y} to {last.day} {last:%B %Y}"


def _window(trip: Trip) -> str:
    if trip.earliest_date == trip.latest_date:
        return f"{trip.earliest_date:%a %d %b}"
    return f"{trip.earliest_date:%d %b} - {trip.latest_date:%d %b}"


def _display(path: Path) -> str:
    """Show paths inside the project relative to it, for shorter output."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)

"""Generate the reproducible BusBidder Spain sample dataset.

Writes four files to data/ (or --out):

- companies.json       the five operators
- destinations.json    the fifteen destinations served from Madrid
- offers.csv           bus offers, including a small set of deliberately invalid rows
- injected_errors.json which rows are invalid and why (for testing and the report)

The script is standalone (standard library only, no import of busbidder): it
plays the role of an external data supplier, so it can produce records the
application must reject. Company behaviour is encoded here, not in
companies.json; the application only ever sees the resulting offers.

Usage:
    python scripts/generate_data.py [--seed N] [--out DIR]

The same seed gives the same files. Python guarantees the seeding method and
random() itself across versions, but not every helper built on it, so exact
output is only promised for the same Python minor version.
"""

import argparse
import csv
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "data"
DEFAULT_SEED = 4420

START_DATE = date(2026, 7, 8)  
NUM_DAYS = 12

COMPANIES = [
    {"company_id": "SOL", "name": "SolRuta", "profile": "Low-cost daytime services"},
    {"company_id": "CAM", "name": "Camino Express", "profile": "Fast direct connections between major cities"},
    {"company_id": "COS", "name": "CostaLink", "profile": "Strong coverage of coastal destinations"},
    {"company_id": "VER", "name": "VerdeBus", "profile": "Environment-focused services and modern vehicles"},
    {"company_id": "NOC", "name": "NocheVia", "profile": "Overnight and late-evening services"},
]


DESTINATIONS = [
    {"destination_id": "BCN", "name": "Barcelona", "region": "Catalonia", "coastal": True, "distance_km": 620, "base_duration_min": 465},
    {"destination_id": "VLC", "name": "Valencia", "region": "Valencian Community", "coastal": True, "distance_km": 360, "base_duration_min": 255},
    {"destination_id": "SEV", "name": "Seville", "region": "Andalusia", "coastal": False, "distance_km": 530, "base_duration_min": 375},
    {"destination_id": "MAL", "name": "Malaga", "region": "Andalusia", "coastal": True, "distance_km": 530, "base_duration_min": 360},
    {"destination_id": "GRA", "name": "Granada", "region": "Andalusia", "coastal": False, "distance_km": 420, "base_duration_min": 285},
    {"destination_id": "COR", "name": "Cordoba", "region": "Andalusia", "coastal": False, "distance_km": 400, "base_duration_min": 270},
    {"destination_id": "BIL", "name": "Bilbao", "region": "Basque Country", "coastal": True, "distance_km": 400, "base_duration_min": 285},
    {"destination_id": "SSB", "name": "San Sebastian", "region": "Basque Country", "coastal": True, "distance_km": 450, "base_duration_min": 330},
    {"destination_id": "ZAR", "name": "Zaragoza", "region": "Aragon", "coastal": False, "distance_km": 320, "base_duration_min": 225},
    {"destination_id": "ALC", "name": "Alicante", "region": "Valencian Community", "coastal": True, "distance_km": 420, "base_duration_min": 300},
    {"destination_id": "MUR", "name": "Murcia", "region": "Region of Murcia", "coastal": False, "distance_km": 400, "base_duration_min": 290},
    {"destination_id": "SAL", "name": "Salamanca", "region": "Castile and Leon", "coastal": False, "distance_km": 215, "base_duration_min": 150},
    {"destination_id": "TOL", "name": "Toledo", "region": "Castilla-La Mancha", "coastal": False, "distance_km": 75, "base_duration_min": 60},
    {"destination_id": "SCQ", "name": "Santiago de Compostela", "region": "Galicia", "coastal": False, "distance_km": 600, "base_duration_min": 495},
    {"destination_id": "CAD", "name": "Cadiz", "region": "Andalusia", "coastal": True, "distance_km": 660, "base_duration_min": 450},
]

MAJOR_CITIES = {"BCN", "VLC", "SEV", "MAL", "BIL", "ZAR", "ALC"}

OFFER_FIELDS = [
    "offer_id", "company_id", "destination_id",
    "departure_date", "departure_time", "arrival_date", "arrival_time",
    "price_eur", "transfers", "fare_type", "changeable", "refundable", "luggage_kg",
    "available_seats", "rating", "co2_kg",
]

BASE_FARE_EUR = 3.0
PRICE_PER_KM = 0.065

FARE_TYPES = ("basic", "standard", "flex")
FARE_PRICE_FACTOR = {"basic": 1.00, "standard": 1.15, "flex": 1.35}
FARE_RULES = {  
    "basic": (False, False, 10),
    "standard": (True, False, 20),
    "flex": (True, True, 30),
}

SERVICE_PROBABILITY = 0.9 
WEEKEND_SURCHARGE = 0.12  
TRANSFER_DISCOUNT = 0.08 
SEAT_RANGE = (1, 45)


@dataclass(frozen=True)
class Behaviour:
    """How one company operates one route. Times are minutes after midnight."""

    price_factor: float 
    duration_factor: float 
    window: tuple[int, int] 
    departures_per_day: int
    transfer_weights: tuple[float, float, float]  
    fare_weights: tuple[float, float, float]  
    rating_mean: float  
    co2_per_km: float  
    co2_reported: float 


def hm(hours: int, minutes: int = 0) -> int:
    return hours * 60 + minutes


def behaviour_for(company_id: str, destination: dict) -> Behaviour:
    """Translate each company profile from the spec into concrete numbers."""
    coastal = destination["coastal"]
    major = destination["destination_id"] in MAJOR_CITIES

    if company_id == "SOL":  
        return Behaviour(0.75, 1.10, (hm(7), hm(17)), 2, (0.60, 0.35, 0.05), (0.60, 0.35, 0.05), 3.6, 0.030, 0.6)
    if company_id == "CAM": 
        if major:
            return Behaviour(1.25, 0.88, (hm(6, 30), hm(21)), 2, (1.00, 0.00, 0.00), (0.10, 0.50, 0.40), 4.3, 0.028, 0.9)
        return Behaviour(1.25, 0.95, (hm(6, 30), hm(21)), 1, (0.50, 0.50, 0.00), (0.10, 0.50, 0.40), 4.3, 0.028, 0.9)
    if company_id == "COS": 
        if coastal:
            return Behaviour(0.85, 0.98, (hm(7), hm(20)), 3, (0.85, 0.15, 0.00), (0.40, 0.45, 0.15), 4.0, 0.030, 0.9)
        return Behaviour(1.10, 1.15, (hm(7), hm(20)), 1, (0.30, 0.60, 0.10), (0.40, 0.45, 0.15), 4.0, 0.030, 0.9)
    if company_id == "VER":  
        return Behaviour(1.10, 1.00, (hm(8), hm(19)), 1, (0.70, 0.30, 0.00), (0.20, 0.50, 0.30), 4.4, 0.012, 1.0)
    if company_id == "NOC": 
        return Behaviour(0.90, 1.20, (hm(20, 30), hm(23, 45)), 1, (0.75, 0.25, 0.00), (0.50, 0.35, 0.15), 3.7, 0.032, 0.3)
    raise ValueError(f"no behaviour defined for company {company_id!r}")


def make_timetable(rng: random.Random, behaviour: Behaviour) -> list[int]:
    """Fixed daily departure times (on the quarter hour) for one company-route pair."""
    start, end = behaviour.window
    slots = list(range(start, end + 1, 15))
    return sorted(rng.sample(slots, behaviour.departures_per_day))


def round_to(value: float, step: float) -> float:
    return round(value / step) * step


def make_offer(
    rng: random.Random, company_id: str, destination: dict, behaviour: Behaviour,
    departure: datetime, seq: int,
) -> dict[str, str]:
    """Build one valid offer row (all values as CSV strings)."""
    transfers = rng.choices((0, 1, 2), weights=behaviour.transfer_weights)[0]
    fare_type = rng.choices(FARE_TYPES, weights=behaviour.fare_weights)[0]
    changeable, refundable, luggage_kg = FARE_RULES[fare_type]
    if company_id == "SOL" and fare_type == "basic":
        luggage_kg = 0 

    duration = destination["base_duration_min"] * behaviour.duration_factor
    duration += sum(rng.randint(35, 75) for _ in range(transfers)) 
    duration = int(round_to(duration * rng.uniform(0.95, 1.05), 5))
    arrival = departure + timedelta(minutes=duration)

    price = (BASE_FARE_EUR + PRICE_PER_KM * destination["distance_km"]) * behaviour.price_factor
    price *= FARE_PRICE_FACTOR[fare_type]
    price *= 1 - TRANSFER_DISCOUNT * transfers
    if departure.weekday() in (4, 6):
        price *= 1 + WEEKEND_SURCHARGE
    price = max(3.0, round_to(price * rng.uniform(0.90, 1.10), 0.5))

    rating = min(5.0, max(1.0, rng.gauss(behaviour.rating_mean, 0.25)))
    co2 = ""
    if rng.random() < behaviour.co2_reported:
        co2 = f"{destination['distance_km'] * (1 + 0.1 * transfers) * behaviour.co2_per_km:.1f}"

    return {
        "offer_id": f"OF-{company_id}-{destination['destination_id']}-{seq:04d}",
        "company_id": company_id,
        "destination_id": destination["destination_id"],
        "departure_date": departure.date().isoformat(),
        "departure_time": departure.strftime("%H:%M"),
        "arrival_date": arrival.date().isoformat(),
        "arrival_time": arrival.strftime("%H:%M"),
        "price_eur": f"{price:.2f}",
        "transfers": str(transfers),
        "fare_type": fare_type,
        "changeable": str(changeable).lower(),
        "refundable": str(refundable).lower(),
        "luggage_kg": str(luggage_kg),
        "available_seats": str(rng.randint(*SEAT_RANGE)),
        "rating": f"{rating:.1f}",
        "co2_kg": co2,
    }


def generate_offers(rng: random.Random) -> list[dict[str, str]]:
    """All valid offers, ordered by company, destination and departure."""
    rows = []
    for company in COMPANIES:
        for destination in DESTINATIONS:
            behaviour = behaviour_for(company["company_id"], destination)
            timetable = make_timetable(rng, behaviour)
            seq = 1
            for day in range(NUM_DAYS):
                travel_date = START_DATE + timedelta(days=day)
                for minutes in timetable:
                    if rng.random() > SERVICE_PROBABILITY:
                        continue
                    departure = datetime.combine(travel_date, datetime.min.time()) + timedelta(minutes=minutes)
                    rows.append(make_offer(rng, company["company_id"], destination, behaviour, departure, seq))
                    seq += 1
    return rows


Override = str | Callable[[dict[str, str]], str]
INVALID_CASES: list[tuple[str, str, dict[str, Override], str]] = [
    ("negative_price", "price_eur", {"price_eur": "-12.50"}, "Price is negative"),
    ("unknown_destination", "destination_id", {"destination_id": "XYZ"}, "Destination code not in destinations.json"),
    ("invalid_date", "departure_date", {"departure_date": "2026-06-31", "arrival_date": "2026-06-31"},
     "Impossible calendar date (June has 30 days); a date-shaped regex would accept it"),
    ("invalid_date", "departure_date", {"departure_date": "14/07/2026"}, "Date not in ISO format YYYY-MM-DD"),
    ("invalid_time", "departure_time", {"departure_time": "25:10"}, "Hour outside 00-23"),
    ("arrival_before_departure", "arrival_time",
     {"departure_time": "14:00", "arrival_date": lambda row: row["departure_date"], "arrival_time": "11:30"},
     "Arrives two and a half hours before it departs, on the same day"),
    ("rating_out_of_scale", "rating", {"rating": "6.5"}, "Rating above the 1-5 scale"),
    ("zero_seats", "available_seats", {"available_seats": "0"}, "No seats available"),
    ("missing_field", "price_eur", {"price_eur": ""}, "Price is empty"),
    ("missing_field", "departure_time", {"departure_time": ""}, "Departure time is empty"),
    ("malformed_id", "offer_id", {"offer_id": lambda row: row["offer_id"][:-4] + "12A"},
     "Sequence part is not four digits"),
    ("malformed_id", "offer_id", {"offer_id": lambda row: row["offer_id"].lower().replace("-", "_")},
     "Lower case with underscores instead of hyphens"),
]
INVALID_SEQ_START = 9001 


def inject_invalid(rng: random.Random, rows: list[dict[str, str]]) -> list[dict]:
    """Insert one invalid row per case at a random position; return the manifest entries."""
    templates = rng.sample(rows, len(INVALID_CASES))
    manifest = []
    for i, (template, (problem, field, overrides, description)) in enumerate(zip(templates, INVALID_CASES)):
        row = dict(template)
        later = {}
        for key, value in overrides.items():
            if callable(value):
                later[key] = value  
            else:
                row[key] = value
        row["offer_id"] = f"OF-{row['company_id']}-{row['destination_id']}-{INVALID_SEQ_START + i:04d}"
        for key, func in later.items():
            row[key] = func(row)

        rows.insert(rng.randint(0, len(rows)), row)
        manifest.append({
            "offer_id": row["offer_id"],
            "problem": problem,
            "field": field,
            "value": row[field],
            "description": description,
        })
    return manifest


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_offers(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OFFER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"random seed (default {DEFAULT_SEED})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default data/)")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed) 
    rows = generate_offers(rng)
    valid_count = len(rows)
    injected = inject_invalid(rng, rows)

    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "companies.json", COMPANIES)
    write_json(args.out / "destinations.json", DESTINATIONS)
    write_offers(args.out / "offers.csv", rows)
    write_json(args.out / "injected_errors.json", {
        "seed": args.seed,
        "date_range": [START_DATE.isoformat(), (START_DATE + timedelta(days=NUM_DAYS - 1)).isoformat()],
        "valid_offers": valid_count,
        "invalid_offers": len(injected),
        "injected": injected,
    })

    print(f"Wrote {valid_count} valid and {len(injected)} invalid offers "
          f"({len(COMPANIES)} companies, {len(DESTINATIONS)} destinations) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

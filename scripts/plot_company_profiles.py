"""Plot how each company's profile shows up in the generated offers.

Reads the data through the application's own loader and validator, so the
figure is based on exactly the valid offers the program uses. Saves
examples/company_profiles.pdf (for the report) and .png.

Usage:
    python scripts/plot_company_profiles.py [--out DIR]

Needs matplotlib, which is a development dependency only: the application
itself uses the standard library.
"""

import argparse
import statistics
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from busbidder.data_io.loader import OFFER_COLUMNS, read_csv_records, read_json_records  
from busbidder.data_io.validator import RecordValidator  
from busbidder.exceptions import RecordValidationError  
from busbidder.models import Offer  

DATA_DIR = PROJECT_ROOT / "data"
COMPANY_ORDER = ["SolRuta", "Camino Express", "CostaLink", "VerdeBus", "NocheVia"]

HIGHLIGHT = "#2a78d6"
CONTEXT = "#b4b2aa"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e1e0d9"
FIGURE_WIDTH_IN = 6.3  


def load_valid_offers() -> list[Offer]:
    """The valid offers, checked by the same validator as the application."""
    validator = RecordValidator()
    companies = {c.company_id: c for c in map(validator.company, _data(DATA_DIR / "companies.json"))}
    destinations = {d.destination_id: d for d in map(validator.destination, _data(DATA_DIR / "destinations.json"))}
    offers = []
    for record in read_csv_records(DATA_DIR / "offers.csv", OFFER_COLUMNS):
        try:
            offers.append(validator.offer(record.data, companies, destinations))
        except RecordValidationError:
            pass  
    return offers


def _data(path: Path) -> list:
    return [record.data for record in read_json_records(path)]


def company_statistics(offers: list[Offer]) -> dict:
    groups: dict[str, list[Offer]] = defaultdict(list)
    for offer in offers:
        groups[offer.company.name].append(offer)
        if offer.company.name == "CostaLink":
            groups["CostaLink (coast)" if offer.destination.coastal else "CostaLink (inland)"].append(offer)

    def minutes(offer: Offer) -> int:
        return offer.departure.hour * 60 + offer.departure.minute

    stats = {}
    for name, group in groups.items():
        co2 = [o.co2_kg / o.destination.distance_km * 1000 for o in group if o.co2_kg is not None]
        stats[name] = {
            "price_per_100km": statistics.mean(o.price_eur / o.destination.distance_km * 100 for o in group),
            "duration_ratio": statistics.mean(o.duration_min / o.destination.base_duration_min for o in group),
            "first_departure": min(map(minutes, group)),
            "last_departure": max(map(minutes, group)),
            "co2_g_per_km": statistics.mean(co2) if co2 else None,
            "co2_reported": len(co2) / len(group),
        }
    return stats


def _clock(minutes: float) -> str:
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


def _style_axis(ax, title: str) -> None:
    ax.set_title(title, loc="left", fontsize=10, color=INK, pad=6)
    ax.tick_params(axis="both", labelsize=8.5, colors=MUTED, length=0)
    ax.tick_params(axis="y", labelcolor=INK)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.invert_yaxis()  


def bar_panel(ax, title, names, values, highlight, label, *, inside=False) -> None:
    """Horizontal bars; only the highlighted bars get a value label (inside the bar end if ``inside``)."""
    colors = [HIGHLIGHT if n in highlight else CONTEXT for n in names]
    ax.barh(names, values, height=0.55, color=colors)
    _style_axis(ax, title)
    right = max(values) * 1.25
    ax.set_xlim(0, right)
    for name, value in zip(names, values):
        if name in highlight:
            if inside:
                ax.text(value - right * 0.02, name, label(value), va="center", ha="right", fontsize=8.5, color="white")
            else:
                ax.text(value + right * 0.015, name, label(value), va="center", fontsize=8.5, color=INK)


def plot(stats: dict, out_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "sans-serif"
    fig, axes = plt.subplots(2, 2, figsize=(FIGURE_WIDTH_IN, 4.6), layout="constrained")

    price_names = ["SolRuta", "Camino Express", "CostaLink (coast)", "CostaLink (inland)", "VerdeBus", "NocheVia"]
    bar_panel(axes[0][0], "Price per 100 km (EUR)", price_names,
              [stats[n]["price_per_100km"] for n in price_names],
              {"SolRuta", "CostaLink (coast)"}, lambda v: f"{v:.1f}")

    ax = axes[0][1]
    bar_panel(ax, "Journey time (line = typical)", COMPANY_ORDER,
              [stats[n]["duration_ratio"] for n in COMPANY_ORDER],
              {"Camino Express"}, lambda v: f"{v:.2f}×", inside=True)
    ax.axvline(1.0, color=MUTED, linewidth=0.8)

    ax = axes[1][0]
    highlight = {"SolRuta", "NocheVia"}
    for name in COMPANY_ORDER:
        first, last = stats[name]["first_departure"], stats[name]["last_departure"]
        color = HIGHLIGHT if name in highlight else CONTEXT
        ax.barh(name, last - first, left=first, height=0.55, color=color)
        span = f"{_clock(first)}–{_clock(last)}"
        if name in highlight and last - first >= 6 * 60:  # wide enough: label inside the bar
            ax.text((first + last) / 2, name, span, va="center", ha="center", fontsize=8.5, color="white")
        elif name in highlight:  # narrow bar: label to its left
            ax.text(first - 20, name, span, va="center", ha="right", fontsize=8.5, color=INK)
    _style_axis(ax, "First to last departure")
    ax.set_xlim(0, 24 * 60)
    ax.set_xticks(range(0, 24 * 60 + 1, 6 * 60), [_clock(m) for m in range(0, 24 * 60 + 1, 6 * 60)])

    bar_panel(axes[1][1], "CO₂ per km (g)", COMPANY_ORDER,
              [stats[n]["co2_g_per_km"] for n in COMPANY_ORDER],
              {"VerdeBus"}, lambda v: f"{v:.0f} g")

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / "company_profiles.pdf", out_dir / "company_profiles.png"]
    for path in paths:
        fig.savefig(path, dpi=300, facecolor="white", metadata={"CreationDate": None} if path.suffix == ".pdf" else None)
    plt.close(fig)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "examples", help="output folder (default examples/)")
    args = parser.parse_args(argv)
    try:
        import matplotlib  
    except ImportError:
        print("This script needs matplotlib: pip install matplotlib", file=sys.stderr)
        return 1

    offers = load_valid_offers()
    stats = company_statistics(offers)
    for name in COMPANY_ORDER:
        s = stats[name]
        print(f"{name:<16} {s['price_per_100km']:5.1f} EUR/100km  {s['duration_ratio']:.2f}x  "
              f"{_clock(s['first_departure'])}-{_clock(s['last_departure'])}  "
              f"{s['co2_g_per_km']:.0f} g/km ({s['co2_reported']:.0%} reported)")
    for path in plot(stats, args.out):
        print(f"Saved {path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path}")
    print(f"Based on {len(offers)} valid offers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

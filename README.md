# BusBidder Spain

A Python application that filters and ranks fictional bus offers from Madrid
using a transparent weighted scoring model. Final project for ACIT4420
(Problem-solving with scripting), OsloMet.

> Work in progress: project setup and the domain model are in place; data
> loading, filtering, ranking and booking follow.

## Requirements

- Python 3.11 or newer (developed with 3.13)
- No third-party runtime libraries (standard library only)
- `pytest` for the tests (see `requirements.txt`)

## Setup

From the project root:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
```

`pip install -e .` makes the `busbidder` package importable from anywhere.
It is optional: the commands below also work without it (see *Running*).

## Running

```bash
python -m busbidder
```

Without the editable install, either set `PYTHONPATH=src` first or run the
entry file directly: `python src/busbidder/__main__.py`. In VS Code, use the
**BusBidder** launch configuration (Run and Debug panel) or "Run Python File"
on `src/busbidder/__main__.py`.

## Tests

```bash
python -m pytest
```

## Project layout

| Path | Contents |
|---|---|
| `src/busbidder/` | Application package |
| `src/busbidder/models/` | Domain classes (Company, Destination, Offer, ...) |
| `src/busbidder/data_io/` | Loading and validating data files |
| `src/busbidder/filtering/`, `ranking/`, `booking/` | Later tasks |
| `data/` | Input data (companies, destinations, offers) |
| `config/` | `settings.json` and traveller profiles |
| `logs/` | Log file `busbidder.log` (created at run time) |
| `scripts/generate_data.py` | Reproducible dataset generator |
| `tests/` | pytest test suite |

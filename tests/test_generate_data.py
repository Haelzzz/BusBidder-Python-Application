"""Tests for the dataset generator (scripts/generate_data.py)."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_data.py"


@pytest.fixture(scope="module")
def generator():
    # scripts/ is not a package, so load the script as a module from its path.
    spec = importlib.util.spec_from_file_location("generate_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate(generator, out: Path, seed: int = 4420) -> dict[str, bytes]:
    generator.main(["--seed", str(seed), "--out", str(out)])
    return {path.name: path.read_bytes() for path in out.iterdir()}


def test_same_seed_gives_identical_files(generator, tmp_path: Path) -> None:
    assert generate(generator, tmp_path / "a") == generate(generator, tmp_path / "b")


def test_different_seed_gives_different_offers(generator, tmp_path: Path) -> None:
    a = generate(generator, tmp_path / "a", seed=1)
    b = generate(generator, tmp_path / "b", seed=2)
    assert a["offers.csv"] != b["offers.csv"]
    assert a["companies.json"] == b["companies.json"]  # reference data does not depend on the seed


def test_every_company_serves_every_destination(generator, tmp_path: Path) -> None:
    generate(generator, tmp_path)
    with (tmp_path / "offers.csv").open(newline="", encoding="utf-8") as f:
        pairs = {(row["company_id"], row["destination_id"]) for row in csv.DictReader(f)}
    assert len({pair for pair in pairs if pair[1] != "XYZ"}) == 5 * 15


def test_manifest_matches_injected_rows(generator, tmp_path: Path) -> None:
    generate(generator, tmp_path)
    manifest = json.loads((tmp_path / "injected_errors.json").read_text(encoding="utf-8"))
    with (tmp_path / "offers.csv").open(newline="", encoding="utf-8") as f:
        rows = {row["offer_id"]: row for row in csv.DictReader(f)}

    assert len(rows) == manifest["valid_offers"] + manifest["invalid_offers"]
    for entry in manifest["injected"]:
        assert rows[entry["offer_id"]][entry["field"]] == entry["value"]

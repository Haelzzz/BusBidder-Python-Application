"""Well-known project locations.

Paths are resolved from this file's location (src/busbidder/paths.py), so the
program finds data/, config/ and logs/ regardless of the current working
directory. This assumes the program runs from the source tree.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
PROFILES_DIR = CONFIG_DIR / "profiles"
LOGS_DIR = PROJECT_ROOT / "logs"

SETTINGS_FILE = CONFIG_DIR / "settings.json"
LOG_FILE = LOGS_DIR / "busbidder.log"

"""Entry point for ``python -m busbidder``.

Also works when this file is run directly (e.g. VS Code's "Run Python File"),
in which case the ``src`` directory is added to ``sys.path`` first.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from busbidder.cli import main  

if __name__ == "__main__":
    raise SystemExit(main())

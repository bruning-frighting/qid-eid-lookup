#!/usr/bin/env python
"""Standalone convenience script: (re)build data/qid_eid.db from the raw CSV.

Usage:
    python scripts/build_database.py [path/to/mapping.csv] [--database PATH]

Defaults to importing data/raw/qid_eid_mapping.csv with --replace, so this
script always produces a clean database from scratch.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qidlookup.cli.commands import app  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "data" / "raw" / "qid_eid_mapping.csv"


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        args = [str(DEFAULT_CSV), *args]
    argv = ["import", "--replace", *args]
    app(argv)


if __name__ == "__main__":
    main()

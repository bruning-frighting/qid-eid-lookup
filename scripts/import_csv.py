#!/usr/bin/env python
"""Standalone convenience script: import a CSV without installing the package.

Usage:
    python scripts/import_csv.py path/to/mapping.csv [--replace] [--database PATH]

Equivalent to: qidlookup import path/to/mapping.csv [--replace]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qidlookup.cli.commands import app  # noqa: E402


def main() -> None:
    argv = ["import", *sys.argv[1:]]
    app(argv)


if __name__ == "__main__":
    main()

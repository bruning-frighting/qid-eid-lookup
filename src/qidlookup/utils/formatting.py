"""Rendering of Mapping records as human-readable text, JSON, CSV, or TSV."""

from __future__ import annotations

import csv
import io
import json
import sys
from collections.abc import Sequence

from qidlookup.core.models import Mapping

_COLUMN_GAP = 3


def should_use_color(no_color: bool, stream=sys.stdout) -> bool:
    """Decide whether ANSI color should be emitted.

    Color is disabled when explicitly requested via --no-color, or when
    the output stream is not a terminal (e.g. redirected to a file).
    """
    if no_color:
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


class Colorizer:
    """Wraps text in ANSI color codes, or passes it through unchanged."""

    _CODES = {"red": "31", "yellow": "33", "green": "32", "bold": "1"}

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, color: str) -> str:
        if not self.enabled:
            return text
        code = self._CODES.get(color, "0")
        return f"\033[{code}m{text}\033[0m"


def format_table(rows: Sequence[dict[str, str]], columns: Sequence[tuple[str, str]]) -> str:
    """Render rows as an aligned, human-readable table.

    Args:
        rows: dicts keyed by the same keys referenced in ``columns``.
        columns: ordered (header, key) pairs.
    """
    if not rows:
        return "(no results)"

    headers = [header for header, _ in columns]
    keys = [key for _, key in columns]

    str_rows = [[_stringify(row.get(key)) for key in keys] for row in rows]

    widths = [len(header) for header in headers]
    for str_row in str_rows:
        for i, cell in enumerate(str_row):
            widths[i] = max(widths[i], len(cell))

    def pad_row(cells: list[str]) -> str:
        return (" " * _COLUMN_GAP).join(
            cell.ljust(widths[i]) if i < len(widths) - 1 else cell
            for i, cell in enumerate(cells)
        )

    lines = [pad_row(headers)]
    for str_row in str_rows:
        lines.append(pad_row(str_row))
    return "\n".join(lines)


def format_json(mappings: Sequence[Mapping]) -> str:
    return json.dumps([m.to_dict() for m in mappings], indent=2)


def format_delimited(mappings: Sequence[Mapping], delimiter: str) -> str:
    output = io.StringIO()
    fieldnames = [
        "qid",
        "eid",
        "devicetypeid",
        "event_category",
        "event_name",
        "description",
        "severity",
        "high_level_category",
        "low_level_category",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=delimiter, lineterminator="\n")
    writer.writeheader()
    for mapping in mappings:
        writer.writerow(mapping.to_dict())
    return output.getvalue()


def _stringify(value: object) -> str:
    if value is None:
        return ""
    return str(value)

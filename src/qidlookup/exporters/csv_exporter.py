"""Streaming exporters for mapping data (CSV, TSV, JSON).

Export always streams from the repository's ``iter_all`` generator rather
than materializing the full result set in memory, so exporting a
multi-million-row database does not blow up RAM usage.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from qidlookup.database.repository import MappingRepository

_FIELDNAMES = [
    "qid",
    "eid",
    "event_category",
    "event_name",
    "description",
    "severity",
    "high_level_category",
    "low_level_category",
]


def export_delimited(
    repository: MappingRepository,
    output_path: Path,
    delimiter: str = ",",
) -> int:
    """Export mappings to a CSV/TSV file. Returns the number of rows written."""
    count = 0
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDNAMES, delimiter=delimiter)
        writer.writeheader()
        for mapping in repository.iter_all():
            row = mapping.to_dict()
            row.pop("devicetypeid", None)
            writer.writerow(row)
            count += 1
    return count


def export_json(
    repository: MappingRepository,
    output_path: Path,
) -> int:
    """Export mappings to a JSON array file, streamed row by row.

    Returns the number of rows written.
    """
    count = 0
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("[\n")
        first = True
        for mapping in repository.iter_all():
            if not first:
                handle.write(",\n")
            row = mapping.to_dict()
            row.pop("devicetypeid", None)
            handle.write(json.dumps(row, indent=2))
            first = False
            count += 1
        handle.write("\n]\n" if not first else "]\n")
    return count

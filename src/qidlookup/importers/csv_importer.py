"""CSV -> SQLite importer for QRadar QID/EID mapping exports.

Two import modes are supported:

* Append (default): rows are inserted into the existing database inside a
  single transaction. If anything raises mid-import, the transaction is
  rolled back and the database is left exactly as it was.
* Replace (``--replace``): the entire dataset is rebuilt into a fresh
  temporary database file, which is only swapped in for the real database
  (via an atomic ``os.replace``) after the import fully succeeds. If the
  import fails at any point, the original database is untouched.
"""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from qidlookup.core.models import ImportResult, Mapping
from qidlookup.database.connection import get_connection, initialize_database
from qidlookup.database.repository import MappingRepository
from qidlookup.utils.validation import (
    RowValidationError,
    clean_str,
    parse_optional_int,
    validate_header,
)


@dataclass
class _ImportStats:
    input_rows: int = 0
    invalid: int = 0
    skipped: int = 0
    duplicated: int = 0


def import_csv(csv_path: Path, database_path: Path, replace: bool = False) -> ImportResult:
    """Import a QID/EID mapping CSV into the SQLite database.

    Args:
        csv_path: path to the source CSV file.
        database_path: path to the target SQLite database.
        replace: if True, atomically rebuild the entire database from this
            CSV rather than appending to the existing one.

    Returns:
        An ImportResult summarizing counts of imported/skipped/invalid/
        duplicated rows.

    Raises:
        ValueError: if the CSV header is missing required columns.
        OSError: for filesystem-level failures.
    """
    csv_path = Path(csv_path)
    database_path = Path(database_path)

    if replace:
        return _import_replace(csv_path, database_path)
    return _import_append(csv_path, database_path)


def _import_append(csv_path: Path, database_path: Path) -> ImportResult:
    stats = _ImportStats()
    with get_connection(database_path) as conn:
        repo = MappingRepository(conn)
        try:
            inserted = repo.insert_many(_iter_valid_mappings(csv_path, stats))
            repo.commit()
        except Exception:
            repo.rollback()
            raise
    return ImportResult(
        input_rows=stats.input_rows,
        imported=inserted,
        skipped=stats.skipped,
        invalid=stats.invalid,
        duplicated=stats.duplicated,
        database_path=str(database_path),
    )


def _import_replace(csv_path: Path, database_path: Path) -> ImportResult:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=".qidlookup_import_", suffix=".db", dir=str(database_path.parent)
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    tmp_path.unlink()  # mkstemp creates an empty placeholder; start clean

    stats = _ImportStats()
    try:
        initialize_database(tmp_path)
        with get_connection(tmp_path) as conn:
            repo = MappingRepository(conn)
            try:
                inserted = repo.insert_many(_iter_valid_mappings(csv_path, stats))
                repo.commit()
            except Exception:
                repo.rollback()
                raise
        # Only touch the real database after the temp build fully succeeded.
        os.replace(tmp_path, database_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return ImportResult(
        input_rows=stats.input_rows,
        imported=inserted,
        skipped=stats.skipped,
        invalid=stats.invalid,
        duplicated=stats.duplicated,
        database_path=str(database_path),
    )


def _iter_valid_mappings(csv_path: Path, stats: _ImportStats) -> Iterator[Mapping]:
    """Stream validated Mapping rows from the CSV, updating ``stats`` in place.

    Reading, validating and yielding one row at a time keeps memory usage
    bounded regardless of file size (datasets of 1M+ rows are expected).
    """
    seen: set[tuple] = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_header(reader.fieldnames)

        for row in reader:
            stats.input_rows += 1

            devicetypeid_raw = row.get("devicetypeid")
            eid = clean_str(row.get("eid"))
            category = clean_str(row.get("event_category"))
            qid_raw = row.get("qid")
            name = clean_str(row.get("event_name"))
            description = clean_str(row.get("description"))
            # Optional columns: absent entirely in older 6-column exports,
            # in which case row.get(...) is simply None -- no header check
            # needed for backward compatibility with pre-existing CSVs.
            severity_raw = row.get("severity")
            low_level_category = clean_str(row.get("low_level_category"))
            high_level_category = clean_str(row.get("high_level_category"))

            if not any(
                [devicetypeid_raw, eid, category, qid_raw, name, description,
                 severity_raw, low_level_category, high_level_category]
            ):
                stats.skipped += 1
                continue

            try:
                devicetypeid = parse_optional_int(devicetypeid_raw, "devicetypeid")
                qid = parse_optional_int(qid_raw, "qid")
                severity = parse_optional_int(severity_raw, "severity")
            except RowValidationError:
                stats.invalid += 1
                continue

            dedup_key = (
                devicetypeid, eid, category, qid, name, description,
                severity, low_level_category, high_level_category,
            )
            if dedup_key in seen:
                stats.duplicated += 1
                continue
            seen.add(dedup_key)

            yield Mapping(
                qid=qid,
                eid=eid,
                devicetypeid=devicetypeid,
                event_category=category,
                event_name=name,
                description=description,
                severity=severity,
                low_level_category=low_level_category,
                high_level_category=high_level_category,
            )

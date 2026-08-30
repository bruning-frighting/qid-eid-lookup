"""Domain models shared across the importer, repository, and CLI layers.

The ``Mapping`` model intentionally mirrors the QRadar CSV export schema.
Future data sources (Splunk, Elastic, Sigma, ...) can be normalized into
the same shape -- ``devicetypeid``/``eid`` map naturally onto a generic
``log_source_type``/``event_id`` pairing -- without changing this class's
public shape, keeping ``core.lookup`` and ``core.search`` vendor-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Mapping:
    """A single QID <-> EID mapping row."""

    qid: int | None
    eid: str | None
    devicetypeid: int | None
    event_category: str | None
    event_name: str | None
    description: str | None
    severity: int | None = None
    low_level_category: str | None = None
    high_level_category: str | None = None
    id: int | None = field(default=None, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict suitable for JSON/CSV serialization."""
        return {
            "qid": self.qid,
            "eid": self.eid,
            "devicetypeid": self.devicetypeid,
            "event_category": self.event_category,
            "event_name": self.event_name,
            "description": self.description,
            "severity": self.severity,
            "high_level_category": self.high_level_category,
            "low_level_category": self.low_level_category,
        }


@dataclass(frozen=True)
class ImportResult:
    """Outcome of a CSV import operation."""

    input_rows: int
    imported: int
    skipped: int
    invalid: int
    duplicated: int
    database_path: str

    @property
    def has_errors(self) -> bool:
        return self.invalid > 0


@dataclass(frozen=True)
class DatabaseStats:
    """Aggregate statistics about the mappings table."""

    total_mappings: int
    unique_qids: int
    unique_eids: int
    device_types: int
    categories: int
    null_qid: int
    null_eid: int
    duplicate_rows: int

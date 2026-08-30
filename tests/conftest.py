"""Shared pytest fixtures for the qidlookup test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qidlookup.core.models import Mapping
from qidlookup.database.connection import get_connection
from qidlookup.database.repository import MappingRepository

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "sample_mapping.csv"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "qid_eid.db"


@pytest.fixture
def repo(db_path: Path):
    """Yield a MappingRepository backed by a fresh temp SQLite database."""
    with get_connection(db_path) as conn:
        yield MappingRepository(conn)


def seed(repo: MappingRepository, mappings: list[Mapping]) -> None:
    """Insert mappings and commit -- a small helper used across test modules."""
    repo.insert_many(mappings)
    repo.commit()


SAMPLE_MAPPINGS = [
    Mapping(
        qid=5000849,
        eid="4662",
        devicetypeid=12,
        event_category="Success Audit",
        event_name="Success Audit: An operation was performed on an object",
        description="Success Audit: An operation was performed on an object.",
        severity=3,
        high_level_category="System",
        low_level_category="Process Creation Success",
    ),
    Mapping(
        qid=5000849,
        eid="4662",
        devicetypeid=15,
        event_category="Object Access",
        event_name="Object Access: An operation was performed on an object",
        description="Object Access variant.",
        severity=3,
        high_level_category="System",
        low_level_category="Process Creation Success",
    ),
    Mapping(
        qid=5000850,
        eid="4663",
        devicetypeid=12,
        event_category="Success Audit",
        event_name="Success Audit: An attempt was made to access an object",
        description="Success Audit: An attempt was made to access an object.",
        severity=2,
        high_level_category="Access",
        low_level_category="Object Access Success",
    ),
    Mapping(
        qid=5000843,
        eid="4656",
        devicetypeid=12,
        event_category="Success Audit",
        event_name="Success Audit: A handle to an object was requested",
        description="Success Audit: A handle to an object was requested.",
    ),
    Mapping(
        qid=5000001,
        eid="4688",
        devicetypeid=12,
        event_category="Process Tracking",
        event_name="A new process has been created",
        description="A new process has been created.",
    ),
]

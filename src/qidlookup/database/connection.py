"""SQLite connection management.

This module is the only place that knows how to open a physical database
connection. Swapping the backing store (e.g. to PostgreSQL) later only
requires a new implementation of this module's ``get_connection`` /
``initialize_database`` contract -- ``core.lookup`` and ``core.search``
never import :mod:`sqlite3` directly, they go through
:mod:`qidlookup.database.repository`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from qidlookup.database.schema import initialize_schema


class DatabaseError(Exception):
    """Raised for unrecoverable database access failures."""


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    # Rollback-journal (default) mode is used rather than WAL: it keeps the
    # database as a single file with no -wal/-shm sidecars, which matters
    # for the atomic-replace-via-rename strategy used by --replace imports.
    connection.execute("PRAGMA synchronous = NORMAL;")
    return connection


def initialize_database(database_path: Path) -> None:
    """Ensure the database file, parent directory, and schema all exist."""
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(database_path)
    try:
        initialize_schema(connection)
    finally:
        connection.close()


def connect(database_path: Path) -> sqlite3.Connection:
    """Open a persistent connection with schema guaranteed to exist.

    Unlike :func:`get_connection`, the caller owns the connection's
    lifetime and must close it explicitly. Intended for long-lived
    consumers (e.g. the desktop GUI) that keep a connection open across
    many user actions; short-lived CLI commands should prefer
    :func:`get_connection` instead.

    Raises:
        DatabaseError: if the database file cannot be opened.
    """
    database_path = Path(database_path)
    if not database_path.exists():
        initialize_database(database_path)

    try:
        connection = _connect(database_path)
    except sqlite3.Error as exc:
        raise DatabaseError(f"Unable to open database at {database_path}: {exc}") from exc

    initialize_schema(connection)
    return connection


@contextmanager
def get_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a short-lived SQLite connection with schema guaranteed to exist.

    Raises:
        DatabaseError: if the database file cannot be opened.
    """
    connection = connect(database_path)
    try:
        yield connection
    finally:
        connection.close()

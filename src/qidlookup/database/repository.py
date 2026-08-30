"""Data access layer for the ``mappings`` table.

All SQL lives here and nowhere else. Every query is parameterized -- no
string interpolation of user-controlled values is ever used. This is the
only module that ``core.lookup`` / ``core.search`` talk to; neither of
those modules imports :mod:`sqlite3`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence

from qidlookup.core.models import DatabaseStats, Mapping

_SELECT_COLUMNS = (
    "id, devicetypeid, eid, event_category, qid, event_name, description, "
    "severity, low_level_category, high_level_category"
)

_FETCH_BATCH_SIZE = 1000
_INSERT_BATCH_SIZE = 5000


def _row_to_mapping(row: sqlite3.Row) -> Mapping:
    return Mapping(
        id=row["id"],
        devicetypeid=row["devicetypeid"],
        eid=row["eid"],
        event_category=row["event_category"],
        qid=row["qid"],
        event_name=row["event_name"],
        description=row["description"],
        severity=row["severity"],
        low_level_category=row["low_level_category"],
        high_level_category=row["high_level_category"],
    )


class MappingRepository:
    """Repository for reading and writing QID/EID mapping rows."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    # -- writes ------------------------------------------------------

    def clear_all(self) -> None:
        """Delete every row in the mappings table."""
        self._conn.execute("DELETE FROM mappings;")

    def insert_many(self, mappings: Iterable[Mapping]) -> int:
        """Insert mappings in batches inside the caller's transaction.

        Returns the number of rows inserted. Does not commit; the caller
        controls transaction boundaries so a failed import can roll back
        cleanly.
        """
        sql = (
            "INSERT INTO mappings "
            "(devicetypeid, eid, event_category, qid, event_name, description, "
            "severity, low_level_category, high_level_category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        batch: list[tuple] = []
        inserted = 0
        cursor = self._conn.cursor()
        for mapping in mappings:
            batch.append(
                (
                    mapping.devicetypeid,
                    mapping.eid,
                    mapping.event_category,
                    mapping.qid,
                    mapping.event_name,
                    mapping.description,
                    mapping.severity,
                    mapping.low_level_category,
                    mapping.high_level_category,
                )
            )
            if len(batch) >= _INSERT_BATCH_SIZE:
                cursor.executemany(sql, batch)
                inserted += len(batch)
                batch.clear()
        if batch:
            cursor.executemany(sql, batch)
            inserted += len(batch)
        return inserted

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    # -- reads ---------------------------------------------------------

    def find_by_qid(self, qid: int, device_type: int | None = None) -> list[Mapping]:
        sql = f"SELECT {_SELECT_COLUMNS} FROM mappings WHERE qid = ?"
        params: list = [qid]
        if device_type is not None:
            sql += " AND devicetypeid = ?"
            params.append(device_type)
        cursor = self._conn.execute(sql, params)
        return [_row_to_mapping(row) for row in cursor.fetchall()]

    def find_by_category(
        self,
        low_level_category: str | None = None,
        high_level_category: str | None = None,
        device_type: int | None = None,
    ) -> list[Mapping]:
        """Find all mappings under a QRadar Low/High Level Category.

        At least one of ``low_level_category``/``high_level_category`` must
        be given, or an empty list is returned. Matching is exact
        (case-insensitive) -- for fuzzy/substring matching use ``search``.
        """
        if low_level_category is None and high_level_category is None:
            return []
        sql = f"SELECT {_SELECT_COLUMNS} FROM mappings WHERE 1=1"
        params: list = []
        if low_level_category is not None:
            sql += " AND low_level_category = ? COLLATE NOCASE"
            params.append(low_level_category)
        if high_level_category is not None:
            sql += " AND high_level_category = ? COLLATE NOCASE"
            params.append(high_level_category)
        if device_type is not None:
            sql += " AND devicetypeid = ?"
            params.append(device_type)
        sql += " ORDER BY qid"
        cursor = self._conn.execute(sql, params)
        return [_row_to_mapping(row) for row in cursor.fetchall()]

    def find_by_eid(self, eid: str, device_type: int | None = None) -> list[Mapping]:
        sql = f"SELECT {_SELECT_COLUMNS} FROM mappings WHERE eid = ?"
        params: list = [eid]
        if device_type is not None:
            sql += " AND devicetypeid = ?"
            params.append(device_type)
        cursor = self._conn.execute(sql, params)
        return [_row_to_mapping(row) for row in cursor.fetchall()]

    def find_by_qids(
        self, qids: Sequence[int], device_type: int | None = None
    ) -> list[Mapping]:
        if not qids:
            return []
        placeholders = ",".join("?" for _ in qids)
        sql = f"SELECT {_SELECT_COLUMNS} FROM mappings WHERE qid IN ({placeholders})"
        params: list = list(qids)
        if device_type is not None:
            sql += " AND devicetypeid = ?"
            params.append(device_type)
        cursor = self._conn.execute(sql, params)
        return [_row_to_mapping(row) for row in cursor.fetchall()]

    def find_by_eids(
        self, eids: Sequence[str], device_type: int | None = None
    ) -> list[Mapping]:
        if not eids:
            return []
        placeholders = ",".join("?" for _ in eids)
        sql = f"SELECT {_SELECT_COLUMNS} FROM mappings WHERE eid IN ({placeholders})"
        params: list = list(eids)
        if device_type is not None:
            sql += " AND devicetypeid = ?"
            params.append(device_type)
        cursor = self._conn.execute(sql, params)
        return [_row_to_mapping(row) for row in cursor.fetchall()]

    def search(
        self,
        term: str,
        device_type: int | None = None,
        category: str | None = None,
        low_level_category: str | None = None,
        high_level_category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Mapping]:
        """Case-insensitive substring search over name/description/category.

        The free-text ``term`` also matches ``low_level_category`` and
        ``high_level_category`` in addition to the original three fields,
        so e.g. ``search("process creation")`` finds QIDs whose QRadar
        Low Level Category is "Process Creation Success" even if the raw
        per-log-source ``event_category`` text differs.
        """
        sql = (
            f"SELECT {_SELECT_COLUMNS} FROM mappings "
            "WHERE (event_name LIKE ? ESCAPE '\\' "
            "OR description LIKE ? ESCAPE '\\' "
            "OR event_category LIKE ? ESCAPE '\\' "
            "OR low_level_category LIKE ? ESCAPE '\\' "
            "OR high_level_category LIKE ? ESCAPE '\\')"
        )
        like_term = f"%{_escape_like(term)}%"
        params: list = [like_term, like_term, like_term, like_term, like_term]
        if device_type is not None:
            sql += " AND devicetypeid = ?"
            params.append(device_type)
        if category is not None:
            sql += " AND event_category = ? COLLATE NOCASE"
            params.append(category)
        if low_level_category is not None:
            sql += " AND low_level_category = ? COLLATE NOCASE"
            params.append(low_level_category)
        if high_level_category is not None:
            sql += " AND high_level_category = ? COLLATE NOCASE"
            params.append(high_level_category)
        sql += " ORDER BY qid LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = self._conn.execute(sql, params)
        return [_row_to_mapping(row) for row in cursor.fetchall()]

    def iter_all(
        self, device_type: int | None = None
    ) -> Iterator[Mapping]:
        """Stream all mappings without loading the full result set into RAM."""
        sql = f"SELECT {_SELECT_COLUMNS} FROM mappings"
        params: list = []
        if device_type is not None:
            sql += " WHERE devicetypeid = ?"
            params.append(device_type)
        cursor = self._conn.execute(sql, params)
        while True:
            rows = cursor.fetchmany(_FETCH_BATCH_SIZE)
            if not rows:
                break
            for row in rows:
                yield _row_to_mapping(row)

    # -- stats / validation ---------------------------------------------

    def get_stats(self) -> DatabaseStats:
        row = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(DISTINCT qid) AS unique_qids,
                COUNT(DISTINCT eid) AS unique_eids,
                COUNT(DISTINCT devicetypeid) AS device_types,
                COUNT(DISTINCT event_category) AS categories,
                SUM(CASE WHEN qid IS NULL THEN 1 ELSE 0 END) AS null_qid,
                SUM(CASE WHEN eid IS NULL THEN 1 ELSE 0 END) AS null_eid
            FROM mappings
            """
        ).fetchone()

        dup_row = self._conn.execute(
            """
            SELECT COALESCE(SUM(cnt - 1), 0) AS duplicate_rows FROM (
                SELECT COUNT(*) AS cnt
                FROM mappings
                GROUP BY devicetypeid, eid, event_category, qid, event_name, description,
                    severity, low_level_category, high_level_category
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()

        return DatabaseStats(
            total_mappings=row["total"] or 0,
            unique_qids=row["unique_qids"] or 0,
            unique_eids=row["unique_eids"] or 0,
            device_types=row["device_types"] or 0,
            categories=row["categories"] or 0,
            null_qid=row["null_qid"] or 0,
            null_eid=row["null_eid"] or 0,
            duplicate_rows=dup_row["duplicate_rows"] or 0,
        )

    def table_exists(self) -> bool:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mappings'"
        ).fetchone()
        return row is not None

    def index_names(self) -> list[str]:
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='mappings'"
        )
        return [row["name"] for row in cursor.fetchall()]

    def integrity_check(self) -> list[str]:
        """Run SQLite's built-in integrity check.

        Returns an empty list if the database is healthy, otherwise a list
        of problem descriptions reported by SQLite.
        """
        rows = self._conn.execute("PRAGMA integrity_check;").fetchall()
        messages = [row[0] for row in rows]
        if messages == ["ok"]:
            return []
        return messages


def _escape_like(term: str) -> str:
    """Escape LIKE wildcard characters so raw search input can't inject them."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

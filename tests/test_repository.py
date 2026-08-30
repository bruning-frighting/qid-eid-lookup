"""Tests for qidlookup.database.repository and connection/schema setup."""

from __future__ import annotations

from qidlookup.core.models import Mapping
from qidlookup.database.connection import get_connection
from qidlookup.database.repository import MappingRepository

from conftest import SAMPLE_MAPPINGS, seed


def test_schema_creates_table_and_indexes(db_path):
    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        assert repo.table_exists()
        indexes = set(repo.index_names())
        assert {
            "idx_mappings_qid",
            "idx_mappings_eid",
            "idx_mappings_device",
            "idx_mappings_category",
            "idx_mappings_llc",
            "idx_mappings_hlc",
        } <= indexes


def test_schema_migrates_pre_existing_v1_database(db_path, tmp_path):
    import sqlite3

    # Simulate a database created before severity/LLC/HLC columns existed.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            devicetypeid INTEGER,
            eid TEXT,
            event_category TEXT,
            qid INTEGER,
            event_name TEXT,
            description TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO mappings (devicetypeid, eid, event_category, qid, event_name, description) "
        "VALUES (12, '4662', 'Success Audit', 5000849, 'Name', 'Desc')"
    )
    conn.commit()
    conn.close()

    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(mappings);")}
        assert {"severity", "low_level_category", "high_level_category"} <= columns
        # Pre-existing row survives the migration untouched.
        mapping = repo.find_by_qid(5000849)[0]
        assert mapping.eid == "4662"
        assert mapping.severity is None


def test_find_by_category_low_level(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = repo.find_by_category(low_level_category="Process Creation Success")
    assert {m.qid for m in results} == {5000849}
    assert len(results) == 2


def test_find_by_category_case_insensitive(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = repo.find_by_category(low_level_category="process creation success")
    assert len(results) == 2


def test_find_by_category_no_filters_returns_empty(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert repo.find_by_category() == []


def test_insert_many_and_find_by_qid(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = repo.find_by_qid(5000850)
    assert len(results) == 1
    assert results[0].eid == "4663"


def test_find_by_qid_multiple_mappings_preserved(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = repo.find_by_qid(5000849)
    assert len(results) == 2
    device_types = {m.devicetypeid for m in results}
    assert device_types == {12, 15}


def test_find_by_qid_not_found_returns_empty_list(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert repo.find_by_qid(99999999) == []


def test_find_by_eid(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = repo.find_by_eid("4656")
    assert len(results) == 1
    assert results[0].qid == 5000843


def test_find_by_qid_device_type_filter(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = repo.find_by_qid(5000849, device_type=15)
    assert len(results) == 1
    assert results[0].event_category == "Object Access"


def test_find_by_qids_batch_preserves_all_matches(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = repo.find_by_qids([5000843, 5000850, 99999999])
    qids_found = {m.qid for m in results}
    assert qids_found == {5000843, 5000850}


def test_iter_all_streams_every_row(repo):
    seed(repo, SAMPLE_MAPPINGS)
    rows = list(repo.iter_all())
    assert len(rows) == len(SAMPLE_MAPPINGS)


def test_get_stats(repo):
    seed(repo, SAMPLE_MAPPINGS)
    stats = repo.get_stats()
    assert stats.total_mappings == 5
    assert stats.unique_qids == 4  # 5000849 appears twice
    assert stats.unique_eids == 4  # "4662" appears twice
    assert stats.device_types == 2
    assert stats.null_qid == 0
    assert stats.null_eid == 0


def test_get_stats_counts_null_qid_and_eid(repo):
    seed(
        repo,
        [
            Mapping(
                qid=None,
                eid=None,
                devicetypeid=12,
                event_category="Test",
                event_name="Name",
                description="Desc",
            )
        ],
    )
    stats = repo.get_stats()
    assert stats.null_qid == 1
    assert stats.null_eid == 1


def test_transaction_rollback_leaves_no_partial_data(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert repo.get_stats().total_mappings == 5

    repo.insert_many(
        [
            Mapping(
                qid=9999,
                eid="9999",
                devicetypeid=1,
                event_category="Tmp",
                event_name="Tmp",
                description="Tmp",
            )
        ]
    )
    repo.rollback()

    assert repo.get_stats().total_mappings == 5


def test_integrity_check_reports_ok(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert repo.integrity_check() == []


def test_search_is_parameterized_against_injection(repo):
    seed(repo, SAMPLE_MAPPINGS)
    # A crafted term containing SQL/LIKE metacharacters must not raise or
    # alter query semantics -- it should just fail to match anything.
    results = repo.search("'; DROP TABLE mappings; --")
    assert results == []
    # The table must still exist and be queryable afterwards.
    assert repo.table_exists()
    assert repo.get_stats().total_mappings == 5

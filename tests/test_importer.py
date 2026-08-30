"""Tests for qidlookup.importers.csv_importer."""

from __future__ import annotations

import pytest

from qidlookup.core.models import Mapping
from qidlookup.database.connection import get_connection
from qidlookup.database.repository import MappingRepository
from qidlookup.importers.csv_importer import import_csv

from conftest import SAMPLE_CSV, seed

HEADER = "devicetypeid,eid,event_category,qid,event_name,description\n"


def _write_csv(path, content: str, encoding: str = "utf-8"):
    path.write_text(content, encoding=encoding, newline="")
    return path


def test_import_optional_llc_hlc_columns_are_parsed(tmp_path, db_path):
    content = (
        "devicetypeid,eid,event_category,qid,event_name,description,"
        "severity,high_level_category,low_level_category\n"
        "12,4688,Process Tracking,5000001,A new process has been created,desc,"
        "5,System,Process Creation Success\n"
    )
    csv_path = _write_csv(tmp_path / "with_categories.csv", content)
    result = import_csv(csv_path, db_path)
    assert result.imported == 1

    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        mapping = repo.find_by_qid(5000001)[0]
        assert mapping.severity == 5
        assert mapping.high_level_category == "System"
        assert mapping.low_level_category == "Process Creation Success"


def test_import_without_llc_hlc_columns_defaults_to_none(db_path):
    # SAMPLE_CSV only has the original 6 columns -- backward compatibility.
    import_csv(SAMPLE_CSV, db_path)
    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        mapping = repo.find_by_qid(5000849)[0]
        assert mapping.severity is None
        assert mapping.low_level_category is None
        assert mapping.high_level_category is None


def test_import_valid_csv(db_path):
    result = import_csv(SAMPLE_CSV, db_path)
    assert result.input_rows == 4
    assert result.imported == 4
    assert result.invalid == 0
    assert result.skipped == 0
    assert result.duplicated == 0

    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        assert repo.get_stats().total_mappings == 4


def test_import_empty_csv_header_only(tmp_path, db_path):
    csv_path = _write_csv(tmp_path / "empty.csv", HEADER)
    result = import_csv(csv_path, db_path)
    assert result.input_rows == 0
    assert result.imported == 0


def test_import_invalid_qid_is_counted_and_skipped(tmp_path, db_path):
    content = HEADER + "12,4662,Success Audit,NOT_A_NUMBER,Some Event,Some description\n"
    csv_path = _write_csv(tmp_path / "invalid_qid.csv", content)
    result = import_csv(csv_path, db_path)
    assert result.input_rows == 1
    assert result.invalid == 1
    assert result.imported == 0


def test_import_missing_columns_raises(tmp_path, db_path):
    csv_path = _write_csv(tmp_path / "missing_cols.csv", "devicetypeid,eid,qid\n12,4662,5000849\n")
    with pytest.raises(ValueError, match="missing required column"):
        import_csv(csv_path, db_path)


def test_import_utf8_content_is_preserved(tmp_path, db_path):
    content = HEADER + "12,4662,Success Audit,5000849,Événement de sécurité,Mô tả tiếng Việt\n"
    csv_path = _write_csv(tmp_path / "utf8.csv", content, encoding="utf-8")
    result = import_csv(csv_path, db_path)
    assert result.imported == 1

    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        mapping = repo.find_by_qid(5000849)[0]
        assert mapping.event_name == "Événement de sécurité"
        assert mapping.description == "Mô tả tiếng Việt"


def test_import_comma_in_description_is_handled(tmp_path, db_path):
    content = HEADER + '12,4662,Success Audit,5000849,Some Event,"A description, with a comma"\n'
    csv_path = _write_csv(tmp_path / "comma.csv", content)
    result = import_csv(csv_path, db_path)
    assert result.imported == 1

    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        mapping = repo.find_by_qid(5000849)[0]
        assert mapping.description == "A description, with a comma"


def test_import_duplicate_rows_are_counted_not_reinserted(tmp_path, db_path):
    row = "12,4662,Success Audit,5000849,Some Event,Some description\n"
    content = HEADER + row + row + row
    csv_path = _write_csv(tmp_path / "dupes.csv", content)
    result = import_csv(csv_path, db_path)
    assert result.input_rows == 3
    assert result.imported == 1
    assert result.duplicated == 2


def test_import_distinct_rows_differing_by_device_are_not_duplicates(tmp_path, db_path):
    content = (
        HEADER
        + "12,4662,Success Audit,5000849,Some Event,Some description\n"
        + "15,4662,Object Access,5000849,Some Event,Some description\n"
    )
    csv_path = _write_csv(tmp_path / "distinct.csv", content)
    result = import_csv(csv_path, db_path)
    assert result.imported == 2
    assert result.duplicated == 0


def test_import_large_file_behavior(tmp_path, db_path):
    rows = [HEADER]
    for i in range(3000):
        rows.append(f"12,{4000 + i},Success Audit,{5000000 + i},Event {i},Description {i}\n")
    csv_path = _write_csv(tmp_path / "large.csv", "".join(rows))
    result = import_csv(csv_path, db_path)
    assert result.input_rows == 3000
    assert result.imported == 3000

    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        assert repo.get_stats().total_mappings == 3000
        assert repo.find_by_qid(5001500)[0].eid == "5500"


def test_import_replace_rebuilds_dataset(db_path, tmp_path):
    import_csv(SAMPLE_CSV, db_path)
    with get_connection(db_path) as conn:
        assert MappingRepository(conn).get_stats().total_mappings == 4

    smaller = _write_csv(
        tmp_path / "smaller.csv",
        HEADER + "12,9999,Test,1234567,Only Event,Only description\n",
    )
    result = import_csv(smaller, db_path, replace=True)
    assert result.imported == 1

    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        assert repo.get_stats().total_mappings == 1
        assert repo.find_by_qid(5000849) == []
        assert repo.find_by_qid(1234567)[0].eid == "9999"


def test_import_replace_leaves_old_database_intact_on_failure(db_path, tmp_path):
    import_csv(SAMPLE_CSV, db_path)

    bad_csv = _write_csv(tmp_path / "bad_header.csv", "not,the,right,columns\n1,2,3,4\n")
    with pytest.raises(ValueError):
        import_csv(bad_csv, db_path, replace=True)

    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        assert repo.get_stats().total_mappings == 4
        assert len(repo.find_by_qid(5000849)) == 1


def test_import_append_failure_rolls_back(db_path, monkeypatch):
    import_csv(SAMPLE_CSV, db_path)

    def _boom(self, mappings):
        raise RuntimeError("simulated failure mid-import")

    monkeypatch.setattr(MappingRepository, "insert_many", _boom)

    with pytest.raises(RuntimeError):
        import_csv(SAMPLE_CSV, db_path, replace=False)

    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        assert repo.get_stats().total_mappings == 4

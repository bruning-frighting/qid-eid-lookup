"""Tests for qidlookup.exporters.csv_exporter."""

from __future__ import annotations

import csv
import json

from qidlookup.database.connection import get_connection
from qidlookup.database.repository import MappingRepository
from qidlookup.exporters.csv_exporter import export_delimited, export_json

from conftest import SAMPLE_MAPPINGS, seed


def test_export_csv(tmp_path, db_path):
    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        seed(repo, SAMPLE_MAPPINGS)
        out_path = tmp_path / "out.csv"
        count = export_delimited(repo, out_path, delimiter=",")

    assert count == len(SAMPLE_MAPPINGS)
    with out_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(SAMPLE_MAPPINGS)
    assert rows[0]["qid"] == "5000849"


def test_export_tsv(tmp_path, db_path):
    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        seed(repo, SAMPLE_MAPPINGS)
        out_path = tmp_path / "out.tsv"
        count = export_delimited(repo, out_path, delimiter="\t")

    assert count == len(SAMPLE_MAPPINGS)
    content = out_path.read_text(encoding="utf-8")
    assert "\t" in content.splitlines()[0]


def test_export_json(tmp_path, db_path):
    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        seed(repo, SAMPLE_MAPPINGS)
        out_path = tmp_path / "out.json"
        count = export_json(repo, out_path)

    assert count == len(SAMPLE_MAPPINGS)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data) == len(SAMPLE_MAPPINGS)
    assert data[0]["qid"] == 5000849


def test_export_device_type_filter(tmp_path, db_path):
    with get_connection(db_path) as conn:
        repo = MappingRepository(conn)
        seed(repo, SAMPLE_MAPPINGS)
        out_path = tmp_path / "filtered.csv"
        count = export_delimited(repo, out_path, delimiter=",", device_type=15)

    assert count == 1
    with out_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["devicetypeid"] == "15"

"""End-to-end CLI tests using Typer's CliRunner.

These exercise the full CLI -> core -> database stack, matching the
acceptance-test scenarios from the project spec.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from qidlookup.cli.commands import app

from conftest import SAMPLE_CSV

runner = CliRunner()


def _import_sample(db_path):
    result = runner.invoke(app, ["--database", str(db_path), "import", str(SAMPLE_CSV)])
    assert result.exit_code == 0
    return result


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "qidlookup" in result.output


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "qid" in result.output
    assert "search" in result.output


def test_cli_import(db_path):
    result = _import_sample(db_path)
    assert "Imported   : 4" in result.output


def test_cli_qid_single_found(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "qid", "5000849"])
    assert result.exit_code == 0
    assert "4662" in result.output


def test_cli_eid_single_found(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "eid", "4662"])
    assert result.exit_code == 0
    assert "5000849" in result.output


def test_cli_qid_batch(db_path):
    _import_sample(db_path)
    result = runner.invoke(
        app, ["--database", str(db_path), "qid", "5000843", "5000849", "5000850"]
    )
    assert result.exit_code == 0
    assert "5000843" in result.output
    assert "5000849" in result.output
    assert "5000850" in result.output


def test_cli_eid_batch(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "eid", "4656", "4662", "4663"])
    assert result.exit_code == 0
    assert "5000843" in result.output


def test_cli_qid_not_found_exit_code_1(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "qid", "99999999"])
    assert result.exit_code == 1
    assert "NOT FOUND" in result.output


def test_cli_qid_invalid_input_exit_code_2(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "qid", "not-an-int"])
    assert result.exit_code == 2
    assert "Error" in result.output


def test_cli_qid_partial_batch_mixed_found_and_not_found(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "qid", "5000849", "99999999"])
    assert result.exit_code == 1
    assert "NOT FOUND" in result.output
    assert "4662" in result.output


def test_cli_qid_json_format(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "qid", "5000849", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["qid"] == 5000849


def test_cli_qid_list_from_file(tmp_path, db_path):
    _import_sample(db_path)
    qids_file = tmp_path / "qids.txt"
    qids_file.write_text("5000843\n5000849\n5000850\n", encoding="utf-8")
    result = runner.invoke(app, ["--database", str(db_path), "qid-list", str(qids_file)])
    assert result.exit_code == 0
    assert "5000843" in result.output


def test_cli_eid_list_from_file(tmp_path, db_path):
    _import_sample(db_path)
    eids_file = tmp_path / "eids.txt"
    eids_file.write_text("4656\n4662\n4663\n", encoding="utf-8")
    result = runner.invoke(app, ["--database", str(db_path), "eid-list", str(eids_file)])
    assert result.exit_code == 0
    assert "4656" in result.output


def test_cli_reverse(tmp_path, db_path):
    _import_sample(db_path)
    qids_file = tmp_path / "qids.txt"
    qids_file.write_text("5000849\n", encoding="utf-8")
    result = runner.invoke(app, ["--database", str(db_path), "reverse", str(qids_file)])
    assert result.exit_code == 0
    assert "4662" in result.output


def test_cli_reverse_eid(tmp_path, db_path):
    _import_sample(db_path)
    eids_file = tmp_path / "eids.txt"
    eids_file.write_text("4662\n", encoding="utf-8")
    result = runner.invoke(app, ["--database", str(db_path), "reverse-eid", str(eids_file)])
    assert result.exit_code == 0
    assert "5000849" in result.output


def test_cli_search(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "search", "operation was performed"])
    assert result.exit_code == 0
    assert "5000849" in result.output


def test_cli_search_no_results_exit_code_1(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "search", "nonexistent-term-xyz"])
    assert result.exit_code == 1


def test_cli_search_high_level_category_free_text_and_filter(tmp_path, db_path):
    csv_path = tmp_path / "with_llc.csv"
    csv_path.write_text(
        "devicetypeid,eid,event_category,qid,event_name,description,"
        "severity,high_level_category,low_level_category\n"
        "12,4688,Process Tracking,5000001,A new process has been created,desc,"
        "5,System,Process Creation Success\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["--database", str(db_path), "import", str(csv_path)])
    assert result.exit_code == 0

    free_text = runner.invoke(
        app, ["--database", str(db_path), "search", "process creation success"]
    )
    assert free_text.exit_code == 0
    assert "5000001" in free_text.output

    filtered = runner.invoke(
        app,
        ["--database", str(db_path), "search", "process", "--hlc", "System"],
    )
    assert filtered.exit_code == 0
    assert "5000001" in filtered.output

    filtered_out = runner.invoke(
        app,
        ["--database", str(db_path), "search", "process", "--hlc", "Access"],
    )
    assert filtered_out.exit_code == 1


def test_cli_category_lookup_multiple_qids(tmp_path, db_path):
    csv_path = tmp_path / "category.csv"
    csv_path.write_text(
        "devicetypeid,eid,event_category,qid,event_name,description,"
        "severity,high_level_category,low_level_category\n"
        "12,4688,WindowsAuthServer,5000862,Process Creation,desc,5,System,Process Creation Success\n"
        "15,1,Sysmon,5001828,Process Create,desc,5,System,Process Creation Success\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["--database", str(db_path), "import", str(csv_path)])
    assert result.exit_code == 0

    lookup = runner.invoke(
        app,
        [
            "--database", str(db_path), "category", "Process Creation Success", "--hlc", "System",
        ],
    )
    assert lookup.exit_code == 0
    assert "5000862" in lookup.output
    assert "5001828" in lookup.output
    assert "Unique QIDs (2)" in lookup.output
    assert "Unique EIDs (2)" in lookup.output


def test_cli_category_lookup_combined_form_disambiguates(tmp_path, db_path):
    csv_path = tmp_path / "ambiguous_category.csv"
    csv_path.write_text(
        "devicetypeid,eid,event_category,qid,event_name,description,"
        "severity,high_level_category,low_level_category\n"
        "12,4688,WindowsAuthServer,5000900,Windows Command Exec,desc,5,"
        "System,Command Execution Success\n"
        "20,execve,LinuxAuditServer,5000901,Linux Command Exec,desc,5,"
        "Audit,Command Execution Success\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["--database", str(db_path), "import", str(csv_path)])
    assert result.exit_code == 0

    windows_only = runner.invoke(
        app, ["--database", str(db_path), "category", "System.Command Execution Success"]
    )
    assert windows_only.exit_code == 0
    assert "5000900" in windows_only.output
    assert "5000901" not in windows_only.output

    linux_only = runner.invoke(
        app, ["--database", str(db_path), "category", "Audit.Command Execution Success"]
    )
    assert linux_only.exit_code == 0
    assert "5000901" in linux_only.output
    assert "5000900" not in linux_only.output


def test_cli_category_lookup_not_found_exit_code_1(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "category", "No Such Category"])
    assert result.exit_code == 1
    assert "NOT FOUND" in result.output


def test_cli_category_lookup_requires_llc_or_hlc_exit_code_2(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "category"])
    assert result.exit_code == 2


def test_cli_stats(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "stats"])
    assert result.exit_code == 0
    assert "Total mappings : 4" in result.output


def test_cli_validate(db_path):
    _import_sample(db_path)
    result = runner.invoke(app, ["--database", str(db_path), "validate"])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_cli_export_csv(tmp_path, db_path):
    _import_sample(db_path)
    out_file = tmp_path / "export.csv"
    result = runner.invoke(app, ["--database", str(db_path), "export", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    assert "qid,eid" in out_file.read_text(encoding="utf-8")


def test_cli_export_json(tmp_path, db_path):
    _import_sample(db_path)
    out_file = tmp_path / "export.json"
    result = runner.invoke(app, ["--database", str(db_path), "export", str(out_file)])
    assert result.exit_code == 0
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(data) == 4


def test_cli_export_refuses_overwrite_without_force(tmp_path, db_path):
    _import_sample(db_path)
    out_file = tmp_path / "export.csv"
    out_file.write_text("existing", encoding="utf-8")
    result = runner.invoke(app, ["--database", str(db_path), "export", str(out_file)])
    assert result.exit_code == 2
    assert "already exists" in result.output


def test_cli_import_missing_file_exit_code_2(db_path):
    result = runner.invoke(app, ["--database", str(db_path), "import", "does-not-exist.csv"])
    assert result.exit_code == 2

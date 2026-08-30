"""Typer-based command-line interface for qidlookup.

This module owns argument parsing, output formatting, and exit codes.
It never touches SQLite or the filesystem-level import logic directly --
it always goes through :mod:`qidlookup.core` and :mod:`qidlookup.database`.

Exit codes:
    0 = all requested lookups succeeded / operation succeeded
    1 = partial success (some QIDs/EIDs not found)
    2 = invalid input (bad argument, bad file, bad format)
    3 = system/database error
"""

from __future__ import annotations

import dataclasses
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

import typer

from qidlookup import __version__
from qidlookup.config.settings import DEFAULT_SEARCH_LIMIT, Settings
from qidlookup.core.lookup import LookupService
from qidlookup.core.models import Mapping
from qidlookup.core.search import SearchService
from qidlookup.database.connection import DatabaseError, get_connection
from qidlookup.database.repository import MappingRepository
from qidlookup.exporters.csv_exporter import export_delimited, export_json
from qidlookup.importers.csv_importer import import_csv
from qidlookup.utils.formatting import format_delimited, format_json, format_table
from qidlookup.utils.validation import (
    InputValidationError,
    parse_device_type_arg,
    parse_qid_arg,
    split_category_arg,
    split_csv_arg,
    validate_output_path,
    validate_readable_file,
)

logger = logging.getLogger("qidlookup")

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_INVALID_INPUT = 2
EXIT_SYSTEM_ERROR = 3

app = typer.Typer(
    name="qidlookup",
    help="Offline QID <-> EID lookup tool for QRadar mapping data.",
    add_completion=False,
    no_args_is_help=True,
)


class AppState:
    """Per-invocation state shared across commands via the Typer context."""

    def __init__(self, database: Optional[str], verbose: bool, no_color: bool) -> None:
        self.settings = Settings.resolve(database=database, verbose=verbose, no_color=no_color)
        self.verbose = verbose
        self.no_color = no_color


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"qidlookup {__version__}")
        raise typer.Exit(code=EXIT_OK)


@app.callback()
def main(
    ctx: typer.Context,
    database: Optional[str] = typer.Option(
        None,
        "--database",
        envvar="QIDLOOKUP_DATABASE",
        help="Path to the SQLite database file (default: data/qid_eid.db).",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose (DEBUG) logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable ANSI color output."),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the qidlookup version and exit.",
    ),
) -> None:
    """QID <-> EID Lookup Tool -- offline QRadar QID/Event ID mapping lookup."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    ctx.obj = AppState(database=database, verbose=verbose, no_color=no_color)


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


@contextmanager
def _repo_session(settings: Settings) -> Iterator[MappingRepository]:
    """Open a repository for the duration of a command, or exit(3) on failure."""
    try:
        with get_connection(settings.database_path) as conn:
            yield MappingRepository(conn)
    except DatabaseError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_SYSTEM_ERROR) from exc


def _echo_error(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)


def _write_or_print(text: str, output: Optional[Path]) -> None:
    if output is None:
        typer.echo(text)
        return
    output.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    typer.echo(f"Written to {output}")


def _format_output(mappings: list[Mapping], fmt: str, human_fn) -> str:
    fmt_lower = fmt.lower()
    if fmt_lower == "human":
        return human_fn(mappings)
    if fmt_lower == "json":
        return format_json(mappings)
    if fmt_lower == "csv":
        return format_delimited(mappings, ",")
    if fmt_lower == "tsv":
        return format_delimited(mappings, "\t")
    _echo_error(f"Unknown format: {fmt} (expected human, json, csv, tsv)")
    raise typer.Exit(code=EXIT_INVALID_INPUT)


def _read_ids_from_file(path: Path) -> list[str]:
    resolved = validate_readable_file(path)
    lines = resolved.read_text(encoding="utf-8-sig").splitlines()
    return [line.strip() for line in lines if line.strip()]


def _resolve_output_and_devicetype(
    output: Optional[Path], force: bool, device_type: Optional[str]
) -> tuple[Optional[Path], Optional[int]]:
    out_path = validate_output_path(output, force) if output else None
    device_type_id = parse_device_type_arg(device_type) if device_type else None
    return out_path, device_type_id


# -- human-readable table renderers -----------------------------------------


def _human_qid_single(qid: int, mappings: list[Mapping]) -> str:
    if not mappings:
        return f"QID {qid}: NOT FOUND"

    lines = [f"QID: {qid}", ""]
    if len(mappings) > 1:
        lines.append(f"Mappings found: {len(mappings)}")
        lines.append("")

    rows = [
        {
            "eid": m.eid or "",
            "devicetypeid": "" if m.devicetypeid is None else m.devicetypeid,
            "event_category": m.event_category or "",
            "high_level_category": m.high_level_category or "",
            "low_level_category": m.low_level_category or "",
            "event_name": m.event_name or "",
        }
        for m in mappings
    ]
    columns = [
        ("EID", "eid"),
        ("Device Type", "devicetypeid"),
        ("Category", "event_category"),
        ("High Level Cat.", "high_level_category"),
        ("Low Level Cat.", "low_level_category"),
        ("Event Name", "event_name"),
    ]
    lines.append(format_table(rows, columns))
    return "\n".join(lines)


def _human_eid_single(eid: str, mappings: list[Mapping]) -> str:
    if not mappings:
        return f"EID {eid}: NOT FOUND"

    lines = [f"EID: {eid}", ""]
    if len(mappings) > 1:
        lines.append(f"Mappings found: {len(mappings)}")
        lines.append("")

    rows = [
        {
            "qid": "" if m.qid is None else m.qid,
            "devicetypeid": "" if m.devicetypeid is None else m.devicetypeid,
            "event_category": m.event_category or "",
            "high_level_category": m.high_level_category or "",
            "low_level_category": m.low_level_category or "",
            "event_name": m.event_name or "",
        }
        for m in mappings
    ]
    columns = [
        ("QID", "qid"),
        ("Device Type", "devicetypeid"),
        ("Category", "event_category"),
        ("High Level Cat.", "high_level_category"),
        ("Low Level Cat.", "low_level_category"),
        ("Event Name", "event_name"),
    ]
    lines.append(format_table(rows, columns))
    return "\n".join(lines)


def _human_qid_batch(results: dict[int, list[Mapping]]) -> str:
    rows = []
    for qid, mappings in results.items():
        if not mappings:
            rows.append(
                {
                    "qid": qid,
                    "eid": "NOT FOUND",
                    "high_level_category": "",
                    "low_level_category": "",
                    "event_name": "",
                }
            )
        else:
            for m in mappings:
                rows.append(
                    {
                        "qid": qid,
                        "eid": m.eid or "",
                        "high_level_category": m.high_level_category or "",
                        "low_level_category": m.low_level_category or "",
                        "event_name": m.event_name or "",
                    }
                )
    columns = [
        ("QID", "qid"),
        ("EID", "eid"),
        ("High Level Cat.", "high_level_category"),
        ("Low Level Cat.", "low_level_category"),
        ("Event Name", "event_name"),
    ]
    return format_table(rows, columns)


def _human_eid_batch(results: dict[str, list[Mapping]]) -> str:
    rows = []
    for eid, mappings in results.items():
        if not mappings:
            rows.append(
                {
                    "eid": eid,
                    "qid": "NOT FOUND",
                    "high_level_category": "",
                    "low_level_category": "",
                    "event_name": "",
                }
            )
        else:
            for m in mappings:
                rows.append(
                    {
                        "eid": eid,
                        "qid": "" if m.qid is None else m.qid,
                        "high_level_category": m.high_level_category or "",
                        "low_level_category": m.low_level_category or "",
                        "event_name": m.event_name or "",
                    }
                )
    columns = [
        ("EID", "eid"),
        ("QID", "qid"),
        ("High Level Cat.", "high_level_category"),
        ("Low Level Cat.", "low_level_category"),
        ("Event Name", "event_name"),
    ]
    return format_table(rows, columns)


def _human_search_table(mappings: list[Mapping]) -> str:
    if not mappings:
        return "(no results)"
    rows = [
        {
            "qid": "" if m.qid is None else m.qid,
            "eid": m.eid or "",
            "high_level_category": m.high_level_category or "",
            "low_level_category": m.low_level_category or "",
            "event_name": m.event_name or "",
        }
        for m in mappings
    ]
    columns = [
        ("QID", "qid"),
        ("EID", "eid"),
        ("High Level Cat.", "high_level_category"),
        ("Low Level Cat.", "low_level_category"),
        ("Event Name", "event_name"),
    ]
    return format_table(rows, columns)


def _human_category_result(
    low_level_category: Optional[str],
    high_level_category: Optional[str],
    mappings: list[Mapping],
) -> str:
    lines = []
    if high_level_category:
        lines.append(f"High Level Category: {high_level_category}")
    if low_level_category:
        lines.append(f"Low Level Category: {low_level_category}")
    lines.append("")

    if not mappings:
        lines.append("NOT FOUND")
        return "\n".join(lines)

    unique_qids = sorted({m.qid for m in mappings if m.qid is not None})
    unique_eids = sorted({m.eid for m in mappings if m.eid})
    lines.append(f"Unique QIDs ({len(unique_qids)}): {', '.join(str(q) for q in unique_qids)}")
    lines.append(f"Unique EIDs ({len(unique_eids)}): {', '.join(unique_eids)}")
    lines.append("")

    rows = [
        {
            "qid": "" if m.qid is None else m.qid,
            "eid": m.eid or "",
            "devicetypeid": "" if m.devicetypeid is None else m.devicetypeid,
            "event_name": m.event_name or "",
        }
        for m in mappings
    ]
    columns = [
        ("QID", "qid"),
        ("EID", "eid"),
        ("Device Type", "devicetypeid"),
        ("Event Name", "event_name"),
    ]
    lines.append(format_table(rows, columns))
    return "\n".join(lines)


# -- shared batch logic for qid/eid single, list-file, and reverse commands --


def _handle_qid_lookup(
    ctx: typer.Context,
    raw_values: list[str],
    device_type: Optional[str],
    fmt: str,
    output: Optional[Path],
    force: bool,
) -> None:
    state: AppState = ctx.obj
    if not raw_values:
        _echo_error("Provide at least one QID.")
        raise typer.Exit(code=EXIT_INVALID_INPUT)

    try:
        parsed_qids = [parse_qid_arg(v) for v in raw_values]
        out_path, device_type_id = _resolve_output_and_devicetype(output, force, device_type)
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc

    with _repo_session(state.settings) as repo:
        results = LookupService(repo).lookup_qids(parsed_qids, device_type=device_type_id)

    found_all = all(bool(ms) for ms in results.values())
    flat_mappings = [m for ms in results.values() for m in ms]

    if fmt.lower() == "human" and len(parsed_qids) == 1:
        text = _human_qid_single(parsed_qids[0], results[parsed_qids[0]])
    else:
        human_fn = lambda _mappings: _human_qid_batch(results)  # noqa: E731
        text = _format_output(flat_mappings, fmt, human_fn)

    _write_or_print(text, out_path)
    raise typer.Exit(code=EXIT_OK if found_all else EXIT_PARTIAL)


def _handle_eid_lookup(
    ctx: typer.Context,
    raw_values: list[str],
    device_type: Optional[str],
    fmt: str,
    output: Optional[Path],
    force: bool,
) -> None:
    state: AppState = ctx.obj
    if not raw_values:
        _echo_error("Provide at least one EID.")
        raise typer.Exit(code=EXIT_INVALID_INPUT)

    cleaned_eids = [v.strip() for v in raw_values if v.strip()]

    try:
        out_path, device_type_id = _resolve_output_and_devicetype(output, force, device_type)
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc

    with _repo_session(state.settings) as repo:
        results = LookupService(repo).lookup_eids(cleaned_eids, device_type=device_type_id)

    found_all = all(bool(ms) for ms in results.values())
    flat_mappings = [m for ms in results.values() for m in ms]

    if fmt.lower() == "human" and len(cleaned_eids) == 1:
        text = _human_eid_single(cleaned_eids[0], results[cleaned_eids[0]])
    else:
        human_fn = lambda _mappings: _human_eid_batch(results)  # noqa: E731
        text = _format_output(flat_mappings, fmt, human_fn)

    _write_or_print(text, out_path)
    raise typer.Exit(code=EXIT_OK if found_all else EXIT_PARTIAL)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


@app.command("import")
def import_cmd(
    ctx: typer.Context,
    csv_file: Path = typer.Argument(..., help="Path to the QID/EID mapping CSV file."),
    replace: bool = typer.Option(
        False, "--replace", help="Atomically rebuild the whole database from this CSV."
    ),
) -> None:
    """Import a QRadar QID/EID mapping CSV file into the database."""
    state: AppState = ctx.obj
    try:
        path = validate_readable_file(csv_file)
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc

    try:
        result = import_csv(path, state.settings.database_path, replace=replace)
    except ValueError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc
    except OSError as exc:
        _echo_error(f"Import failed: {exc}")
        raise typer.Exit(code=EXIT_SYSTEM_ERROR) from exc

    typer.echo("Import completed.\n")
    typer.echo(f"Input rows : {result.input_rows}")
    typer.echo(f"Imported   : {result.imported}")
    typer.echo(f"Skipped    : {result.skipped}")
    typer.echo(f"Invalid    : {result.invalid}")
    typer.echo(f"Duplicated : {result.duplicated}")
    typer.echo(f"Database   : {result.database_path}")
    raise typer.Exit(code=EXIT_OK)


@app.command("qid")
def qid_cmd(
    ctx: typer.Context,
    qids: Optional[List[str]] = typer.Argument(None, help="One or more QIDs to look up."),
    qids_opt: Optional[str] = typer.Option(None, "--qids", help="Comma-separated list of QIDs."),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="Filter by device type ID."),
    fmt: str = typer.Option("human", "--format", "-f", help="Output format: human, json, csv, tsv."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write result to a file."),
    force: bool = typer.Option(False, "--force", help="Overwrite --output file if it already exists."),
) -> None:
    """Look up one or more QIDs and show their EID mapping(s)."""
    raw_values = list(qids or [])
    if qids_opt:
        raw_values.extend(split_csv_arg(qids_opt))
    _handle_qid_lookup(ctx, raw_values, device_type, fmt, output, force)


@app.command("eid")
def eid_cmd(
    ctx: typer.Context,
    eids: Optional[List[str]] = typer.Argument(None, help="One or more EIDs to look up."),
    eids_opt: Optional[str] = typer.Option(None, "--eids", help="Comma-separated list of EIDs."),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="Filter by device type ID."),
    fmt: str = typer.Option("human", "--format", "-f", help="Output format: human, json, csv, tsv."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write result to a file."),
    force: bool = typer.Option(False, "--force", help="Overwrite --output file if it already exists."),
) -> None:
    """Look up one or more EIDs and show their QID mapping(s)."""
    raw_values = list(eids or [])
    if eids_opt:
        raw_values.extend(split_csv_arg(eids_opt))
    _handle_eid_lookup(ctx, raw_values, device_type, fmt, output, force)


@app.command("qid-list")
def qid_list_cmd(
    ctx: typer.Context,
    file: Path = typer.Argument(..., help="Text file with one QID per line."),
    device_type: Optional[str] = typer.Option(None, "--device-type"),
    fmt: str = typer.Option("human", "--format", "-f"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Look up every QID listed in a text file (one QID per line)."""
    try:
        raw_values = _read_ids_from_file(file)
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc
    _handle_qid_lookup(ctx, raw_values, device_type, fmt, output, force)


@app.command("eid-list")
def eid_list_cmd(
    ctx: typer.Context,
    file: Path = typer.Argument(..., help="Text file with one EID per line."),
    device_type: Optional[str] = typer.Option(None, "--device-type"),
    fmt: str = typer.Option("human", "--format", "-f"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Look up every EID listed in a text file (one EID per line)."""
    try:
        raw_values = _read_ids_from_file(file)
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc
    _handle_eid_lookup(ctx, raw_values, device_type, fmt, output, force)


@app.command("reverse")
def reverse_cmd(
    ctx: typer.Context,
    file: Path = typer.Argument(..., help="Text file with one QID per line."),
    device_type: Optional[str] = typer.Option(None, "--device-type"),
    fmt: str = typer.Option("human", "--format", "-f"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Reverse lookup: QID list -> all corresponding EID mappings."""
    try:
        raw_values = _read_ids_from_file(file)
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc
    _handle_qid_lookup(ctx, raw_values, device_type, fmt, output, force)


@app.command("reverse-eid")
def reverse_eid_cmd(
    ctx: typer.Context,
    file: Path = typer.Argument(..., help="Text file with one EID per line."),
    device_type: Optional[str] = typer.Option(None, "--device-type"),
    fmt: str = typer.Option("human", "--format", "-f"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Reverse lookup: EID list -> all corresponding QID mappings."""
    try:
        raw_values = _read_ids_from_file(file)
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc
    _handle_eid_lookup(ctx, raw_values, device_type, fmt, output, force)


@app.command("search")
def search_cmd(
    ctx: typer.Context,
    term: str = typer.Argument(..., help="Text to search for in name/description/category."),
    limit: int = typer.Option(DEFAULT_SEARCH_LIMIT, "--limit", help="Maximum number of results."),
    offset: int = typer.Option(0, "--offset", help="Number of results to skip (pagination)."),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="Filter by device type ID."),
    category: Optional[str] = typer.Option(
        None, "--category", help="Filter by exact raw event category (per log source)."
    ),
    low_level_category: Optional[str] = typer.Option(
        None, "--llc", "--low-level-category", help="Filter by exact QRadar Low Level Category."
    ),
    high_level_category: Optional[str] = typer.Option(
        None, "--hlc", "--high-level-category", help="Filter by exact QRadar High Level Category."
    ),
    fmt: str = typer.Option("human", "--format", "-f", help="Output format: human, json, csv, tsv."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write result to a file."),
    force: bool = typer.Option(False, "--force", help="Overwrite --output file if it already exists."),
) -> None:
    """Search event name/description/category (incl. Low/High Level Category) for a text fragment."""
    state: AppState = ctx.obj
    try:
        out_path, device_type_id = _resolve_output_and_devicetype(output, force, device_type)
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc

    with _repo_session(state.settings) as repo:
        mappings = SearchService(repo).search(
            term,
            device_type=device_type_id,
            category=category,
            low_level_category=low_level_category,
            high_level_category=high_level_category,
            limit=limit,
            offset=offset,
        )

    text = _format_output(mappings, fmt, _human_search_table)
    _write_or_print(text, out_path)
    raise typer.Exit(code=EXIT_OK if mappings else EXIT_PARTIAL)


@app.command("category")
def category_cmd(
    ctx: typer.Context,
    low_level_category: Optional[str] = typer.Argument(
        None,
        help="Low Level Category, e.g. 'Process Creation Success', or the combined "
        "QRadar-style 'High Level.Low Level' form, e.g. 'System.Process Creation Success'.",
    ),
    high_level_category: Optional[str] = typer.Option(
        None, "--hlc", "--high-level-category", help="QRadar High Level Category, e.g. 'System'."
    ),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="Filter by device type ID."),
    fmt: str = typer.Option("human", "--format", "-f", help="Output format: human, json, csv, tsv."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write result to a file."),
    force: bool = typer.Option(False, "--force", help="Overwrite --output file if it already exists."),
) -> None:
    """Look up QID/EID mappings by exact QRadar Low and/or High Level Category.

    The same Low Level Category name can exist under different High Level
    Categories (e.g. "Command Execution Success" appears under both
    "Audit" (Linux) and "System" (Windows)) -- pass `--hlc` or the combined
    "High Level.Low Level" form to disambiguate:

        qidlookup category "Process Creation Success" --hlc System
        qidlookup category "System.Process Creation Success"
        qidlookup category "Audit.Command Execution Success"

    Exact match, not substring -- use `search --llc/--hlc` for fuzzy matching.
    """
    state: AppState = ctx.obj
    if not low_level_category and not high_level_category:
        _echo_error("Provide a Low Level Category and/or --hlc.")
        raise typer.Exit(code=EXIT_INVALID_INPUT)

    if high_level_category is None and low_level_category:
        auto_hlc, auto_llc = split_category_arg(low_level_category)
        if auto_hlc is not None:
            high_level_category = auto_hlc
            low_level_category = auto_llc

    try:
        out_path, device_type_id = _resolve_output_and_devicetype(output, force, device_type)
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc

    with _repo_session(state.settings) as repo:
        mappings = LookupService(repo).lookup_by_category(
            low_level_category=low_level_category,
            high_level_category=high_level_category,
            device_type=device_type_id,
        )

    human_fn = lambda ms: _human_category_result(  # noqa: E731
        low_level_category, high_level_category, ms
    )
    text = _format_output(mappings, fmt, human_fn)
    _write_or_print(text, out_path)
    raise typer.Exit(code=EXIT_OK if mappings else EXIT_PARTIAL)


@app.command("stats")
def stats_cmd(
    ctx: typer.Context,
    fmt: str = typer.Option("human", "--format", "-f", help="Output format: human or json."),
) -> None:
    """Show database statistics (row counts, uniqueness, NULLs, duplicates)."""
    state: AppState = ctx.obj
    with _repo_session(state.settings) as repo:
        stats = repo.get_stats()

    if fmt.lower() == "json":
        typer.echo(json.dumps(dataclasses.asdict(stats), indent=2))
    else:
        typer.echo("Database Statistics")
        typer.echo("-" * 28)
        typer.echo("")
        typer.echo(f"Total mappings : {stats.total_mappings}")
        typer.echo(f"Unique QIDs    : {stats.unique_qids}")
        typer.echo(f"Unique EIDs    : {stats.unique_eids}")
        typer.echo(f"Device Types   : {stats.device_types}")
        typer.echo(f"Categories     : {stats.categories}")
        typer.echo("")
        typer.echo(f"NULL QID       : {stats.null_qid}")
        typer.echo(f"NULL EID       : {stats.null_eid}")
        typer.echo(f"Duplicate rows : {stats.duplicate_rows}")
    raise typer.Exit(code=EXIT_OK)


@app.command("validate")
def validate_cmd(ctx: typer.Context) -> None:
    """Validate database integrity: schema, indexes, and SQLite consistency."""
    state: AppState = ctx.obj
    problems: list[str] = []

    with _repo_session(state.settings) as repo:
        if not repo.table_exists():
            problems.append("mappings table is missing")
        else:
            expected_indexes = {
                "idx_mappings_qid",
                "idx_mappings_eid",
                "idx_mappings_device",
                "idx_mappings_category",
            }
            missing_indexes = expected_indexes - set(repo.index_names())
            if missing_indexes:
                problems.append(f"missing indexes: {', '.join(sorted(missing_indexes))}")
            problems.extend(repo.integrity_check())

    if problems:
        typer.echo("Database validation FAILED:")
        for problem in problems:
            typer.echo(f"  - {problem}")
        raise typer.Exit(code=EXIT_SYSTEM_ERROR)

    typer.echo("Database validation OK.")
    raise typer.Exit(code=EXIT_OK)


@app.command("export")
def export_cmd(
    ctx: typer.Context,
    output: Path = typer.Argument(..., help="Output file path (.csv, .tsv, or .json)."),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="Filter by device type ID."),
    force: bool = typer.Option(False, "--force", help="Overwrite the output file if it already exists."),
) -> None:
    """Export the full mapping database (or a filtered subset) to a file."""
    state: AppState = ctx.obj
    try:
        out_path = validate_output_path(output, force)
        device_type_id = parse_device_type_arg(device_type) if device_type else None
    except InputValidationError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=EXIT_INVALID_INPUT) from exc

    suffix = out_path.suffix.lower()
    with _repo_session(state.settings) as repo:
        if suffix == ".json":
            count = export_json(repo, out_path, device_type=device_type_id)
        elif suffix == ".tsv":
            count = export_delimited(repo, out_path, delimiter="\t", device_type=device_type_id)
        elif suffix in (".csv", ""):
            count = export_delimited(repo, out_path, delimiter=",", device_type=device_type_id)
        else:
            _echo_error(f"Unsupported export extension: {suffix} (use .csv, .tsv, or .json)")
            raise typer.Exit(code=EXIT_INVALID_INPUT)

    typer.echo(f"Exported {count} row(s) to {out_path}")
    raise typer.Exit(code=EXIT_OK)


@app.command("gui")
def gui_cmd(ctx: typer.Context) -> None:
    """Launch the desktop GUI (Tkinter) for interactive QID/EID lookup."""
    state: AppState = ctx.obj
    try:
        from qidlookup.gui.app import launch
    except ImportError as exc:
        _echo_error(f"GUI is unavailable: {exc}")
        raise typer.Exit(code=EXIT_SYSTEM_ERROR) from exc

    launch(state.settings.database_path)
    raise typer.Exit(code=EXIT_OK)

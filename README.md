# QID ↔ EID Lookup Tool

An offline, production-quality CLI (and optional desktop GUI) for looking up
mappings between **QRadar QIDs**, vendor event IDs (e.g. **Windows Event
IDs**), and QRadar's **High/Low Level Category** taxonomy — backed by a
local SQLite database built from a QRadar CSV export. No network access or
QRadar connection is required at query time.

## 1. Project purpose

QRadar exports QID ↔ EID mapping tables that analysts need to cross-reference
constantly during detection engineering and incident response — "what QID
does Windows EID 4688 map to?", "what EIDs feed QID 5000849?", "which QIDs
fall under System.Process Creation Success?". This tool turns a raw CSV
export into a fast, indexed, offline-queryable SQLite database with a
scriptable CLI and a desktop GUI, so lookup no longer requires opening
QRadar or grepping a spreadsheet.

Key properties:

- **Offline** — works entirely from a local `.db` file.
- **1:many aware** — a QID can map to multiple EIDs (and vice versa) across
  device types/categories; no mapping is ever silently collapsed or lost.
- **Category-aware** — looks up by QRadar High/Low Level Category, not just
  QID/EID, and correctly disambiguates identically-named Low Level
  Categories that live under different High Level Categories (e.g.
  "Command Execution Success" exists under both `Audit` (Linux) and
  `System` (Windows)).
- **Batch-first** — single lookups, multi-value lookups, and file-based
  lookups all use the same underlying engine.
- **Scriptable** — human, JSON, CSV, and TSV output, proper exit codes.
- **Two front-ends, one engine** — the CLI and the Tkinter desktop GUI are
  both thin presentation layers over the same `core`/`database` code, so
  results are always identical between them.

## 2. Architecture

Strict layering, enforced by import direction — the CLI/GUI never touch SQL,
and the database layer never imports either front-end:

```
CSV file
   │
   ▼
importers/csv_importer.py      (validates + streams rows)
   │
   ▼
database/repository.py         (parameterized SQL only)
   │
   ▼
SQLite (data/qid_eid.db)
   │
   ▼
core/lookup.py, core/search.py (business logic, format-agnostic)
   │
   ▼
exporters/csv_exporter.py      (streaming CSV/TSV/JSON export)
   │
   ├──────────────────────┬─────────────────────┐
   ▼                      ▼
cli/commands.py       gui/app.py            utils/formatting.py
(Typer CLI)           (Tkinter desktop)      (human table / JSON / CSV / TSV)
```

- **`core/`** contains all business logic and is storage-agnostic — it talks
  to `database/repository.py`, never to `sqlite3` directly. Swapping SQLite
  for PostgreSQL later means rewriting `database/connection.py` and
  `database/repository.py` only.
- **`database/`** is the only place SQL lives. All queries are parameterized.
- **`importers/`** and **`exporters/`** stream row-by-row; nothing loads a
  multi-million-row dataset fully into memory.
- **`cli/`** and **`gui/`** own argument parsing, exit codes/dialogs, and
  output formatting only — no lookup/search/import logic lives in either.

### Project tree

```
qid-eid-lookup/
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── data/
│   ├── raw/qid_eid_mapping.csv     # sample QRadar-style export
│   └── qid_eid.db                  # built SQLite database (generated)
├── src/qidlookup/
│   ├── __main__.py                 # `python -m qidlookup` entry point
│   ├── cli/commands.py             # Typer CLI
│   ├── gui/app.py                  # Tkinter desktop GUI
│   ├── core/{models,lookup,search}.py
│   ├── database/{connection,schema,repository}.py
│   ├── importers/csv_importer.py
│   ├── exporters/csv_exporter.py
│   ├── config/settings.py
│   └── utils/{validation,formatting}.py
├── tests/
│   ├── test_importer.py, test_lookup.py, test_search.py,
│   │   test_repository.py, test_exporters.py, test_formatting.py,
│   │   test_validation.py, test_cli.py
│   ├── conftest.py
│   └── fixtures/sample_mapping.csv
└── scripts/
    ├── import_csv.py
    └── build_database.py
```

## 3. Installation

Requires Python 3.9+.

```bash
cd qid-eid-lookup
pip install .
qidlookup --help
```

For development (editable install + test dependencies):

```bash
pip install -e ".[dev]"
```

## 4. Import CSV

```bash
qidlookup import data/raw/qid_eid_mapping.csv
```

```
Import completed.

Input rows : 9
Imported   : 9
Skipped    : 0
Invalid    : 0
Duplicated : 0
Database   : data/qid_eid.db
```

Rebuild the database from scratch (safe, atomic — the old database is
untouched if the import fails partway through):

```bash
qidlookup import data/raw/qid_eid_mapping.csv --replace
```

The CSV needs at least the 6 base columns (`devicetypeid,eid,event_category,
qid,event_name,description`); `severity`, `high_level_category`, and
`low_level_category` are optional and enable the category lookups in
section 8 — see section 11 for how to get those columns out of QRadar.

## 5. QID lookup

```bash
qidlookup qid 5000849
```

```
QID: 5000849

EID    Device Type   Category        High Level Cat.   Low Level Cat.   Event Name
4662   12            Success Audit                                      Success Audit: An operation was performed on an object
```

If not found:

```bash
qidlookup qid 99999999
```

```
QID 99999999: NOT FOUND
```

(exit code `1`)

## 6. EID lookup

```bash
qidlookup eid 4662
```

```
EID: 4662

QID       Device Type   Category        High Level Cat.   Low Level Cat.   Event Name
5000849   12            Success Audit                                      Success Audit: An operation was performed on an object
```

## 7. Batch lookup

Multiple values on the command line, `--qids`/`--eids` comma lists, or a
file with one ID per line:

```bash
qidlookup qid 5000843 5000849 5000850
qidlookup qid --qids 5000843,5000849,5000850
qidlookup qid-list qids.txt
qidlookup eid 4656 4662 4663
qidlookup eid-list eids.txt
qidlookup reverse qids.txt        # alias of qid-list
qidlookup reverse-eid eids.txt    # alias of eid-list
```

```
QID       EID    High Level Cat.   Low Level Cat.   Event Name
5000843   4656                                       Success Audit: A handle to an object was requested
5000849   4662                                       Success Audit: An operation was performed on an object
5000850   4663                                       Success Audit: An attempt was made to access an object
```

Not-found entries are shown inline and never abort the batch:

```
QID       EID          Event Name
5000849   4662         ...
9999999   NOT FOUND
```

Exit code reflects the overall outcome: `0` if every value was found, `1`
if any were not found.

## 8. Category lookup (High/Low Level Category → QID/EID)

QRadar's Low Level Category names are **not unique** across High Level
Categories — e.g. "Command Execution Success" exists under both `Audit`
(Linux) and `System` (Windows). The `category` command looks up by the
combination, so the two never get confused:

```bash
qidlookup category "Process Creation Success" --hlc System
qidlookup category "System.Process Creation Success"       # combined form, same result
qidlookup category "Audit.Command Execution Success"       # disambiguates from System's
```

```
High Level Category: System
Low Level Category: Process Creation Success

Unique QIDs (2): 5000862, 5001828
Unique EIDs (2): 1, 4688

QID       EID    Device Type   Event Name
5000862   4688   12            Process Creation
5001828   1      15            Process Create
```

- Passing just a Low Level Category name (no `--hlc`, no dot) matches that
  name under **any** High Level Category — fine when the name happens to
  be unique in your dataset, ambiguous otherwise.
- The combined `"High Level.Low Level"` form (matching how QRadar displays
  it) is parsed automatically and is equivalent to passing `--hlc` separately.
- Matching is **exact** (case-insensitive), not substring — for fuzzy
  matching, use `search --llc/--hlc` (section 9) instead.
- Not found → `NOT FOUND`, exit code `1`. Neither a category nor `--hlc`
  given → exit code `2`.

## 9. Search

```bash
qidlookup search "handle to an object"
qidlookup search "object" --limit 50
qidlookup search "object" --device-type 12
qidlookup search "object" --category "Success Audit"      # raw, per-log-source category
qidlookup search "process" --hlc System                   # High Level Category filter
qidlookup search "process" --llc "Process Creation Success"  # Low Level Category filter
```

Search is case-insensitive and matches `event_name`, `description`,
`event_category`, `low_level_category`, and `high_level_category` —
`--category`/`--llc`/`--hlc` narrow results down with an exact-match filter
on top of the free-text term.

## 10. Export

```bash
qidlookup export mappings.csv
qidlookup export mappings.json
qidlookup export windows.csv --device-type 12
```

Format is inferred from the file extension (`.csv`, `.tsv`, `.json`).
Export streams from the database and never loads the full table into
memory, so it scales to 1M+ rows. Existing files are not overwritten unless
`--force` is passed.

Other commands also support `--format json|csv|tsv --output file --force`
for scripting, e.g.:

```bash
qidlookup qid-list qids.txt --format csv --output result.csv
qidlookup category "System.Process Creation Success" --format json --output result.json
```

## 11. Database structure

SQLite, single file (`data/qid_eid.db` by default):

```sql
CREATE TABLE mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    devicetypeid INTEGER,
    eid TEXT,
    event_category TEXT,        -- raw, per-log-source category (e.g. "Snort")
    qid INTEGER,
    event_name TEXT,
    description TEXT,
    severity INTEGER,
    low_level_category TEXT,    -- QRadar Low Level Category (e.g. "Process Creation Success")
    high_level_category TEXT    -- QRadar High Level Category (e.g. "System")
);

CREATE INDEX idx_mappings_qid      ON mappings(qid);
CREATE INDEX idx_mappings_eid      ON mappings(eid);
CREATE INDEX idx_mappings_device   ON mappings(devicetypeid);
CREATE INDEX idx_mappings_category ON mappings(event_category);
CREATE INDEX idx_mappings_llc      ON mappings(low_level_category);
CREATE INDEX idx_mappings_hlc      ON mappings(high_level_category);
```

`event_category` (raw, source-specific) and `low_level_category`/
`high_level_category` (QRadar's standardized taxonomy) are different
fields — a base QRadar export only has the former unless it's joined
against `qidmap`/`category_type` in the source database (see below).
Databases created before these three columns existed are migrated
automatically (columns added in place, existing rows untouched) the next
time the tool opens them — no manual migration step required.

QID↔EID is treated as many-to-many: a QID may appear multiple times (e.g.
once per device type), and lookups always return the full set of matching
rows rather than assuming a single answer.

### Getting Low/High Level Category from QRadar

The base CSV export only has 6 columns. To also get `severity` and the
standardized Low/High Level Category names, dump directly from QRadar's
Postgres backend (adjust table/column names for your version — verify with
`\d qidmap` / `\d category_type` first, since internal schema can differ
between QRadar versions):

```sql
\copy (
  SELECT
    qem.devicetypeid, qem.eid, qem.event_category, qem.qid,
    qem.event_name, qem.description, qm.severity,
    hlc.name_i18n_key AS high_level_category,
    llc.name_i18n_key AS low_level_category
  FROM qid_eid_mapping qem
  LEFT JOIN qidmap qm         ON qm.qid = qem.qid
  LEFT JOIN category_type llc ON qm.lowlevelcategory = llc.id
  LEFT JOIN category_type hlc ON llc.parent_id = hlc.id
) TO '/tmp/qid_eid_full_mapping.csv' WITH CSV HEADER
```

`category_type` is a self-referencing tree: rows with `parent_id IS NULL`
are High Level Categories, rows with a `parent_id` are Low Level
Categories whose parent is their High Level Category (despite the column
being named `name_i18n_key`, some QRadar deployments store the plain
display text there directly — verify with a sample `SELECT` before
trusting it blindly). Import the result the same way as any other export:

```bash
qidlookup import qid_eid_full_mapping.csv --replace
```

Extra columns (`severity`, `high_level_category`, `low_level_category`)
are optional — importing an older 6-column CSV still works fine, those
fields just stay `NULL`.

Inspect or repair:

```bash
qidlookup stats       # row counts, uniqueness, NULLs, duplicate rows
qidlookup validate    # schema/index presence + SQLite integrity_check
```

Database path resolution order: `--database PATH` > `QIDLOOKUP_DATABASE`
env var > `data/qid_eid.db` (relative to the project root, not the CWD).

## 12. Desktop GUI

For interactive use (no terminal), a Tkinter desktop GUI is included —
it's a thin presentation layer over the same `core`/`database` modules the
CLI uses, so results are always identical.

```bash
qidlookup gui
```

or, after `pip install .`:

```bash
qidlookup-gui
```

The window has six tabs:

- **QID Lookup** / **EID Lookup** — paste one or many IDs (comma- or
  newline-separated), optional device-type filter, results in a
  sortable table, export button (CSV/TSV/JSON).
- **Category Lookup** — look up by Low Level Category (optionally with a
  High Level Category to disambiguate). Type the combined
  `"System.Process Creation Success"` form directly and it auto-splits,
  same as the CLI. Shows a "Unique QIDs / Unique EIDs" summary plus the
  full detail table.
- **Search** — free-text search with device-type/category/LLC/HLC/limit
  filters.
- **Import CSV** — browse to a CSV file, toggle `--replace`, see the same
  import summary (imported/skipped/invalid/duplicated) the CLI prints.
- **Stats** — database statistics, refreshable.

The database path shown at the top follows the same resolution as the CLI
(`QIDLOOKUP_DATABASE` env var, then `data/qid_eid.db`); use **Browse...**
to point it at a different `.db` file without restarting.

## 13. Development

```bash
pip install -e ".[dev]"
qidlookup import tests/fixtures/sample_mapping.csv --replace
qidlookup qid 5000849
```

Style: type hints on public functions, docstrings on public APIs,
parameterized SQL only, no business logic in the CLI/GUI layers.

## 14. Testing

```bash
pytest
pytest --cov=qidlookup --cov-report=term-missing
```

100+ tests covering importer edge cases (empty CSV, invalid QID, missing
columns, UTF-8, commas in descriptions, duplicates, large files, replace
safety, rollback, optional severity/LLC/HLC columns), lookup (found/
not-found/multi-mapping/batch/category disambiguation), search
(case-insensitivity, partial match, limit, category filters), export
(CSV/TSV/JSON), repository (indexes, transactions, SQL-injection
resistance, schema migration), input validation, and full CLI
integration — at **89% line coverage** (target: ≥85%; the Tkinter GUI is
excluded from the coverage metric — see `pyproject.toml`'s
`[tool.coverage.run]` — since it's UI wiring smoke-tested manually, same
rationale as not unit-testing widget layout).

## 15. Build Windows EXE

```bash
pip install pyinstaller
pyinstaller --onefile --name qidlookup src/qidlookup/__main__.py
```

For the GUI, build a windowed executable (`--windowed` suppresses the
console window since it's not needed for a GUI app):

```bash
pyinstaller --onefile --windowed --name qidlookup-gui src/qidlookup/gui/app.py
```

Both resolve their database path the same way as running from source
(`--database`, then `QIDLOOKUP_DATABASE`, then a default next to the
executable) — no absolute paths are hard-coded. To keep the database
alongside the executable:

```bash
dist\qidlookup.exe --database .\qid_eid.db import qid_eid_mapping.csv --replace
dist\qidlookup.exe --database .\qid_eid.db qid 5000849
dist\qidlookup-gui.exe
```

## 16. Updating the dataset

```
QRadar → export → qid_eid_mapping.csv → qidlookup import --replace → SQLite → Lookup Tool
```

```bash
qidlookup import new_qid_eid_mapping.csv --replace
```

`--replace` builds the new dataset in a temporary file and only swaps it
in atomically after the import fully succeeds. If the import fails for any
reason (bad header, disk error, etc.), the existing database is left
completely untouched.

## 17. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Error: QID must be an integer.` | A non-numeric value was passed to `qid`/`--qids`. |
| `Error: CSV header is missing required column(s): ...` | The CSV doesn't match the QRadar export schema (`devicetypeid,eid,event_category,qid,event_name,description`). |
| `Error: Output file already exists: ... (use --force to overwrite)` | Pass `--force` to overwrite, or choose a different `--output` path. |
| `Error: Provide a Low Level Category and/or --hlc.` | `category` needs at least one of the positional argument or `--hlc`. |
| `category`/`search --llc`/`--hlc` returns nothing but data looks right | The imported CSV didn't have `low_level_category`/`high_level_category` columns — check with `qidlookup stats` (or re-import a CSV that has them, see section 11). |
| Same Low Level Category name returns mappings from the wrong OS/vendor | Disambiguate with `--hlc` or the combined `"High Level.Low Level"` form (section 8). |
| `Database validation FAILED` | Run `qidlookup validate` for details; if indexes are missing, re-import with `--replace` to rebuild them. |
| Exit code `1` on lookup | Normal — it means at least one requested QID/EID/category was not found; check output for `NOT FOUND` entries. |
| Exit code `3` | Database/system-level error (e.g. unreadable/corrupt `.db` file). |
| `qidlookup: command not found` (PowerShell) | The Python Scripts folder isn't on PATH — use `python -m qidlookup ...` instead, or add the Scripts folder to PATH. |

## Future extension points

The current schema mirrors QRadar's QID/EID/category export, but nothing in
`core/` or the CLI/GUI assumes "Windows" or "QRadar" specifically:

- `devicetypeid`/`eid` generalize to `log_source_type`/`event_id`; `low_level_category`/
  `high_level_category` generalize to any vendor's severity/category taxonomy.
- Additional sources (Splunk, Elastic, Sigma) can be normalized into the
  same `Mapping` shape and imported through a new module under
  `importers/` without touching `core/lookup.py`, `core/search.py`, or
  either front-end.
- The repository layer (`database/repository.py`) is the only place aware
  of SQLite; a PostgreSQL-backed repository could implement the same
  method surface (`find_by_qid`, `find_by_eid`, `find_by_category`,
  `search`, `iter_all`, ...) as a drop-in replacement.

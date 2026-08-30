# QID ↔ EID Lookup Tool

An offline CLI and desktop GUI for looking up IBM QRadar mappings in three ways:

1. **QID lookup** — find EIDs from a QRadar QID.
2. **EID lookup** — find QIDs from a vendor Event ID.
3. **Category lookup** — find QID/EID mappings from a High Level and/or Low Level Category.

All lookups use a local SQLite database. No QRadar connection is required after the data is imported.

## Install

Requires Python 3.9 or newer and [Git LFS](https://git-lfs.com/).

```powershell
git lfs install
git clone https://github.com/bruning-frighting/qid-eid-lookup.git
cd qid-eid-lookup
git lfs pull
python -m pip install -e .
```

If `qidlookup` is not available in your `PATH`, use `python -m qidlookup` instead.

## Default database and custom data

The repository includes a ready-to-use default database at `data/qid_eid.db`. It is stored with Git LFS because the file is about 271 MB. After cloning, you can start looking up data immediately:

```powershell
qidlookup stats
qidlookup eid 7045 --device-type 12
```

If you have a custom QRadar CSV, replace the default database with:

```powershell
qidlookup import path/to/custom_qid_eid_mapping.csv --replace
```

`--replace` builds the new database safely and swaps it in only after the import succeeds. Keep a copy of the original database if you want to restore it later, or run `git lfs pull` again after deleting the custom database.

Category lookup requires a CSV containing `high_level_category` and `low_level_category`.

## 1. QID lookup

Use this mode when you already know the **QRadar QID**.

```powershell
qidlookup qid 5000849
qidlookup qid 5000849 --device-type 12
qidlookup qid 5000843 5000849 5000850
```

In the GUI, open **QID Lookup**, enter one or more QIDs, and click **Lookup QID**.

## 2. EID lookup

Use this mode for a Windows Event ID or another vendor **Event ID**.

```powershell
qidlookup eid 4662
qidlookup eid 7045
qidlookup eid 7045 --device-type 12
```

In the GUI, open **EID Lookup**, enter one or more Event IDs, and click **Lookup EID**.

> Windows Event ID `7045` is an **EID**, not a QID. In the current full dataset, filtering EID `7045` by Device Type `12` returns QID `5001613` (`A service was installed in a system`).

The same QID or EID may have multiple mappings. Use `--device-type` or the GUI's **Device Type** field to narrow the results.

## 3. Category lookup

Category matching is exact and case-insensitive.

Look up a Low Level Category:

```powershell
qidlookup category "Command Execution Success"
```

Look up a High Level Category:

```powershell
qidlookup category --hlc Audit
```

Use both levels for a more precise result:

```powershell
qidlookup category "Command Execution Success" --hlc Audit
```

The combined `High Level.Low Level` form is equivalent:

```powershell
qidlookup category "Audit.Command Execution Success"
```

In the current full dataset, `Audit.Command Execution Success` exists, while `System.Command Execution Success` does not.

In the GUI, open **Category Lookup** and either:

- Enter the Low Level and High Level Category in separate fields, or
- Enter `Audit.Command Execution Success` in the Low Level field and leave the High Level field empty.

Do not use the combined form and a separate High Level value at the same time.

## Start the GUI

```powershell
qidlookup gui
```

or:

```powershell
qidlookup-gui
```

Use **Browse...** and **Open** at the top of the window to select another SQLite database.

## Output and batch lookup

Lookup commands support human-readable, JSON, CSV, and TSV output:

```powershell
qidlookup eid 7045 --format json
qidlookup qid 5000849 --format csv --output result.csv
qidlookup category "Audit.Command Execution Success" --format json
```

For files containing one ID per line:

```powershell
qidlookup qid-list qids.txt
qidlookup eid-list eids.txt
```

## CSV format

Required columns:

```text
devicetypeid,eid,event_category,qid,event_name,description
```

Optional columns:

```text
severity,high_level_category,low_level_category
```

Without the two category columns, QID and EID lookup still work, but Category Lookup returns no results.

## Useful commands

```powershell
qidlookup search "service was installed"
qidlookup stats
qidlookup validate
```

- `search` finds text in event names, descriptions, and categories.
- `stats` shows database counts and missing data.
- `validate` checks the SQLite schema, indexes, and integrity.

## Test

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

## License

MIT License. See [LICENSE](LICENSE).

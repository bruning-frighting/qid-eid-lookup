"""Tkinter desktop GUI for qidlookup.

Reuses the exact same layers the CLI uses (``core.lookup``,
``core.search``, ``database.repository``, ``importers.csv_importer``,
``exporters`` formatting helpers) -- this module only builds widgets and
wires button clicks to those existing services. No SQL, no CSV parsing,
and no lookup logic lives here.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from qidlookup import __version__
from qidlookup.config.settings import Settings
from qidlookup.core.lookup import LookupService
from qidlookup.core.models import Mapping
from qidlookup.core.search import SearchService
from qidlookup.database.connection import DatabaseError, connect
from qidlookup.database.repository import MappingRepository
from qidlookup.importers.csv_importer import import_csv
from qidlookup.utils.formatting import format_delimited, format_json
from qidlookup.utils.validation import (
    InputValidationError,
    parse_qid_arg,
    split_category_arg,
    validate_readable_file,
)

_COLUMNS = (
    "qid",
    "eid",
    "event_category",
    "severity",
    "high_level_category",
    "low_level_category",
    "event_name",
    "description",
)
_HEADINGS = {
    "qid": "QID",
    "eid": "EID",
    "event_category": "Category",
    "severity": "Severity",
    "high_level_category": "High Level Cat.",
    "low_level_category": "Low Level Cat.",
    "event_name": "Event Name",
    "description": "Description",
}
_WIDTHS = {"qid": 90, "eid": 90, "severity": 60}


class QidLookupApp(tk.Tk):
    """Main application window."""

    def __init__(self, initial_db_path: Optional[Path] = None) -> None:
        super().__init__()
        self.title(f"QID <-> EID Lookup Tool v{__version__}")
        self.geometry("1050x680")
        self.minsize(800, 500)

        self.settings = Settings.resolve()
        self.repo: Optional[MappingRepository] = None
        self.stats_text: Optional[tk.Text] = None

        self._build_db_bar()
        self._build_notebook()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._connect_db(initial_db_path or self.settings.database_path)

    # -- database connection lifecycle -----------------------------------

    def _connect_db(self, path) -> None:
        path = Path(path)
        try:
            new_conn = connect(path)
        except DatabaseError as exc:
            messagebox.showerror("Database Error", str(exc))
            return

        if self.repo is not None:
            self.repo.commit()  # no-op if nothing pending; keeps close() clean
        if self.repo is not None:
            try:
                self.repo._conn.close()  # noqa: SLF001 - GUI owns connection lifetime
            except Exception:
                pass

        self.repo = MappingRepository(new_conn)
        self.db_path_var.set(str(path))
        self._refresh_stats()
        self.status_var.set(f"Connected: {path}")

    def _on_close(self) -> None:
        if self.repo is not None:
            try:
                self.repo._conn.close()  # noqa: SLF001
            except Exception:
                pass
        self.destroy()

    # -- top bar: database selector ---------------------------------------

    def _build_db_bar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)

        ttk.Label(bar, text="Database:").pack(side="left")
        self.db_path_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.db_path_var, width=65).pack(side="left", padx=4)
        ttk.Button(bar, text="Browse...", command=self._browse_db).pack(side="left")
        ttk.Button(
            bar, text="Open", command=lambda: self._connect_db(self.db_path_var.get())
        ).pack(side="left", padx=4)

        self.status_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.status_var, foreground="#666666").pack(
            side="left", padx=12
        )

    def _browse_db(self) -> None:
        path = filedialog.askopenfilename(
            title="Chọn database SQLite",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if path:
            self._connect_db(path)

    # -- notebook (tabs) ----------------------------------------------------

    def _build_notebook(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=4)

        self._build_lookup_tab(notebook, "QID Lookup", is_qid=True)
        self._build_lookup_tab(notebook, "EID Lookup", is_qid=False)
        self._build_category_tab(notebook)
        self._build_search_tab(notebook)
        self._build_import_tab(notebook)
        self._build_stats_tab(notebook)

    # -- shared: results table ----------------------------------------------

    def _build_results_table(self, parent) -> tuple[ttk.Frame, ttk.Treeview]:
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=_COLUMNS, show="headings", height=16)
        for col in _COLUMNS:
            tree.heading(col, text=_HEADINGS[col])
            tree.column(col, width=_WIDTHS.get(col, 220), anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return frame, tree

    @staticmethod
    def _populate_table(tree: ttk.Treeview, mappings: list[Mapping]) -> None:
        tree.delete(*tree.get_children())
        for m in mappings:
            tree.insert(
                "",
                "end",
                values=(
                    "" if m.qid is None else m.qid,
                    m.eid or "",
                    m.event_category or "",
                    "" if m.severity is None else m.severity,
                    m.high_level_category or "",
                    m.low_level_category or "",
                    m.event_name or "",
                    m.description or "",
                ),
            )

    def _export_mappings(self, mappings: list[Mapping]) -> None:
        if not mappings:
            messagebox.showinfo("Export", "Không có kết quả để export.")
            return
        path = filedialog.asksaveasfilename(
            title="Export kết quả",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("TSV", "*.tsv"), ("JSON", "*.json")],
        )
        if not path:
            return
        suffix = Path(path).suffix.lower()
        try:
            if suffix == ".json":
                content = format_json(mappings)
            elif suffix == ".tsv":
                content = format_delimited(mappings, "\t")
            else:
                content = format_delimited(mappings, ",")
            Path(path).write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Export Error", str(exc))
            return
        messagebox.showinfo("Export", f"Đã export {len(mappings)} dòng vào:\n{path}")

    def _require_repo(self) -> Optional[MappingRepository]:
        if self.repo is None:
            messagebox.showerror("Database", "Chưa kết nối được database.")
            return None
        return self.repo

    # -- QID / EID lookup tab -------------------------------------------------

    def _build_lookup_tab(self, notebook: ttk.Notebook, title: str, is_qid: bool) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=8, pady=6)

        id_label = "QID" if is_qid else "EID"
        ttk.Label(
            top, text=f"Nhập {id_label} (cách nhau bằng dấu phẩy hoặc xuống dòng):"
        ).pack(anchor="w")

        text_input = tk.Text(top, height=4, width=90)
        text_input.pack(fill="x", pady=4)

        result_frame, tree = self._build_results_table(frame)

        status_var = tk.StringVar()
        state: dict = {"last_mappings": []}

        def do_lookup() -> None:
            repo = self._require_repo()
            if repo is None:
                return

            raw_text = text_input.get("1.0", "end")
            raw_values = [v.strip() for v in raw_text.replace(",", "\n").splitlines() if v.strip()]
            if not raw_values:
                messagebox.showwarning("Input", f"Nhập ít nhất một {id_label}.")
                return

            try:
                if is_qid:
                    parsed = [parse_qid_arg(v) for v in raw_values]
                    results = LookupService(repo).lookup_qids(parsed)
                else:
                    results = LookupService(repo).lookup_eids(raw_values)
            except InputValidationError as exc:
                messagebox.showerror("Input Error", str(exc))
                return

            flat = [m for ms in results.values() for m in ms]
            not_found = [str(k) for k, ms in results.items() if not ms]
            self._populate_table(tree, flat)
            state["last_mappings"] = flat

            summary = f"{len(flat)} mapping tìm thấy cho {len(results)} {id_label} đã nhập."
            if not_found:
                preview = ", ".join(not_found[:10]) + ("..." if len(not_found) > 10 else "")
                summary += f"  Không tìm thấy ({len(not_found)}): {preview}"
            status_var.set(summary)

        def do_clear() -> None:
            text_input.delete("1.0", "end")
            tree.delete(*tree.get_children())
            state["last_mappings"] = []
            status_var.set("")

        btns = ttk.Frame(top)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text=f"Lookup {id_label}", command=do_lookup).pack(side="left")
        ttk.Button(
            btns, text="Export kết quả...", command=lambda: self._export_mappings(state["last_mappings"])
        ).pack(side="left", padx=4)
        ttk.Button(btns, text="Xóa", command=do_clear).pack(side="left")

        result_frame.pack(fill="both", expand=True, padx=8, pady=6)
        ttk.Label(frame, textvariable=status_var, foreground="#666666").pack(
            anchor="w", padx=8, pady=(0, 6)
        )

    # -- category (LLC/HLC) lookup tab ------------------------------------------

    def _build_category_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Category Lookup")

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=8, pady=6)

        ttk.Label(
            top,
            text="Tra QID/EID theo QRadar Category (khớp chính xác). Có thể gõ "
            "\"Audit.Command Execution Success\" vào ô Low Level, tool tự tách High/Low:",
        ).pack(anchor="w")

        opts = ttk.Frame(top)
        opts.pack(fill="x", pady=4)
        ttk.Label(opts, text="Low Level Category:").pack(side="left")
        llc_var = tk.StringVar()
        llc_entry = ttk.Entry(opts, textvariable=llc_var, width=32)
        llc_entry.pack(side="left", padx=4)
        ttk.Label(opts, text="High Level Category (tùy chọn):").pack(side="left", padx=(12, 0))
        hlc_var = tk.StringVar()
        ttk.Entry(opts, textvariable=hlc_var, width=24).pack(side="left", padx=4)
        result_frame, tree = self._build_results_table(frame)
        status_var = tk.StringVar()
        state: dict = {"last_mappings": []}

        def do_lookup() -> None:
            repo = self._require_repo()
            if repo is None:
                return

            llc = llc_var.get().strip() or None
            hlc = hlc_var.get().strip() or None
            if hlc is None and llc:
                auto_hlc, auto_llc = split_category_arg(llc)
                if auto_hlc is not None:
                    hlc, llc = auto_hlc, auto_llc
            if not llc and not hlc:
                messagebox.showwarning(
                    "Input", "Nhập Low Level Category và/hoặc High Level Category."
                )
                return

            results = LookupService(repo).lookup_by_category(
                low_level_category=llc, high_level_category=hlc
            )
            self._populate_table(tree, results)
            state["last_mappings"] = results

            if not results:
                status_var.set("NOT FOUND")
            else:
                unique_qids = sorted({m.qid for m in results if m.qid is not None})
                unique_eids = sorted({m.eid for m in results if m.eid})
                status_var.set(
                    f"Unique QIDs ({len(unique_qids)}): {', '.join(str(q) for q in unique_qids)}"
                    f"   |   Unique EIDs ({len(unique_eids)}): {', '.join(unique_eids)}"
                )

        llc_entry.bind("<Return>", lambda _event: do_lookup())

        btns = ttk.Frame(top)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="Lookup", command=do_lookup).pack(side="left")
        ttk.Button(
            btns, text="Export kết quả...", command=lambda: self._export_mappings(state["last_mappings"])
        ).pack(side="left", padx=4)

        result_frame.pack(fill="both", expand=True, padx=8, pady=6)
        ttk.Label(frame, textvariable=status_var, foreground="#666666").pack(
            anchor="w", padx=8, pady=(0, 6)
        )

    # -- search tab -----------------------------------------------------------

    def _build_search_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Search")

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=8, pady=6)

        ttk.Label(
            top,
            text="Từ khóa (tìm trong event name / description / category / "
            "Low & High Level Category):",
        ).pack(anchor="w")
        term_var = tk.StringVar()
        term_entry = ttk.Entry(top, textvariable=term_var, width=70)
        term_entry.pack(fill="x", pady=4)

        opts = ttk.Frame(top)
        opts.pack(fill="x", pady=2)
        ttk.Label(opts, text="Category:").pack(side="left")
        category_var = tk.StringVar()
        ttk.Entry(opts, textvariable=category_var, width=18).pack(side="left", padx=4)
        ttk.Label(opts, text="Limit:").pack(side="left", padx=(12, 0))
        limit_var = tk.StringVar(value="100")
        ttk.Entry(opts, textvariable=limit_var, width=6).pack(side="left", padx=4)

        opts2 = ttk.Frame(top)
        opts2.pack(fill="x", pady=2)
        ttk.Label(opts2, text="High Level Category (chính xác):").pack(side="left")
        hlc_var = tk.StringVar()
        ttk.Entry(opts2, textvariable=hlc_var, width=20).pack(side="left", padx=4)
        ttk.Label(opts2, text="Low Level Category (chính xác):").pack(side="left", padx=(12, 0))
        llc_var = tk.StringVar()
        ttk.Entry(opts2, textvariable=llc_var, width=20).pack(side="left", padx=4)

        result_frame, tree = self._build_results_table(frame)
        status_var = tk.StringVar()
        state: dict = {"last_mappings": []}

        def do_search() -> None:
            repo = self._require_repo()
            if repo is None:
                return

            term = term_var.get().strip()
            if not term:
                messagebox.showwarning("Input", "Nhập từ khóa tìm kiếm.")
                return

            try:
                limit = int(limit_var.get()) if limit_var.get().strip() else 100
            except ValueError as exc:
                messagebox.showerror("Input Error", str(exc))
                return

            category = category_var.get().strip() or None
            high_level_category = hlc_var.get().strip() or None
            low_level_category = llc_var.get().strip() or None
            results = SearchService(repo).search(
                term,
                category=category,
                low_level_category=low_level_category,
                high_level_category=high_level_category,
                limit=limit,
            )
            self._populate_table(tree, results)
            state["last_mappings"] = results
            status_var.set(f"Tìm thấy {len(results)} kết quả (limit={limit}).")

        term_entry.bind("<Return>", lambda _event: do_search())

        btns = ttk.Frame(top)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="Search", command=do_search).pack(side="left")
        ttk.Button(
            btns, text="Export kết quả...", command=lambda: self._export_mappings(state["last_mappings"])
        ).pack(side="left", padx=4)

        result_frame.pack(fill="both", expand=True, padx=8, pady=6)
        ttk.Label(frame, textvariable=status_var, foreground="#666666").pack(
            anchor="w", padx=8, pady=(0, 6)
        )

    # -- import tab -------------------------------------------------------------

    def _build_import_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Import CSV")

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=8, pady=6)

        ttk.Label(top, text="File CSV nguồn (QRadar export):").pack(anchor="w")
        row = ttk.Frame(top)
        row.pack(fill="x", pady=4)
        path_var = tk.StringVar()
        ttk.Entry(row, textvariable=path_var, width=75).pack(side="left", fill="x", expand=True)

        def browse_csv() -> None:
            chosen = filedialog.askopenfilename(
                title="Chọn file CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")]
            )
            if chosen:
                path_var.set(chosen)

        ttk.Button(row, text="Browse...", command=browse_csv).pack(side="left", padx=4)

        replace_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top,
            text="--replace (rebuild toàn bộ database; an toàn nếu import lỗi giữa chừng)",
            variable=replace_var,
        ).pack(anchor="w", pady=4)

        result_text = tk.Text(frame, height=16, state="disabled")
        result_text.pack(fill="both", expand=True, padx=8, pady=6)

        def do_import() -> None:
            csv_value = path_var.get().strip()
            if not csv_value:
                messagebox.showwarning("Input", "Chọn file CSV trước.")
                return
            try:
                validated = validate_readable_file(csv_value)
            except InputValidationError as exc:
                messagebox.showerror("Input Error", str(exc))
                return

            if not messagebox.askyesno(
                "Xác nhận Import",
                f"Import:\n{validated}\n\nvào database:\n{self.settings.database_path}\n\n"
                f"--replace = {replace_var.get()}",
            ):
                return

            # Release our connection first: --replace atomically renames a
            # new file over the database path, which a held-open handle
            # could interfere with on some platforms.
            if self.repo is not None:
                try:
                    self.repo._conn.close()  # noqa: SLF001
                except Exception:
                    pass
                self.repo = None

            self.config(cursor="watch")
            self.update_idletasks()
            try:
                result = import_csv(
                    validated, self.settings.database_path, replace=replace_var.get()
                )
                message = (
                    "Import completed.\n\n"
                    f"Input rows : {result.input_rows}\n"
                    f"Imported   : {result.imported}\n"
                    f"Skipped    : {result.skipped}\n"
                    f"Invalid    : {result.invalid}\n"
                    f"Duplicated : {result.duplicated}\n"
                    f"Database   : {result.database_path}\n"
                )
            except (ValueError, OSError) as exc:
                message = f"Import FAILED: {exc}\n"
            finally:
                self.config(cursor="")

            result_text.configure(state="normal")
            result_text.insert("end", message + ("-" * 60) + "\n")
            result_text.see("end")
            result_text.configure(state="disabled")

            self._connect_db(self.settings.database_path)

        ttk.Button(top, text="Import", command=do_import).pack(anchor="w", pady=4)

    # -- stats tab ----------------------------------------------------------------

    def _build_stats_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Stats")

        self.stats_text = tk.Text(frame, height=16, width=50, state="disabled")
        self.stats_text.pack(padx=12, pady=12, anchor="nw")

        ttk.Button(frame, text="Refresh", command=self._refresh_stats).pack(
            anchor="w", padx=12
        )

    def _refresh_stats(self) -> None:
        if self.repo is None or self.stats_text is None:
            return
        stats = self.repo.get_stats()
        text = (
            "Database Statistics\n"
            + "-" * 28
            + "\n\n"
            f"Total mappings : {stats.total_mappings}\n"
            f"Unique QIDs    : {stats.unique_qids}\n"
            f"Unique EIDs    : {stats.unique_eids}\n"
            f"Categories     : {stats.categories}\n\n"
            f"NULL QID       : {stats.null_qid}\n"
            f"NULL EID       : {stats.null_eid}\n"
            f"Duplicate rows : {stats.duplicate_rows}\n"
        )
        self.stats_text.configure(state="normal")
        self.stats_text.delete("1.0", "end")
        self.stats_text.insert("1.0", text)
        self.stats_text.configure(state="disabled")


def launch(database_path: Optional[Path] = None) -> None:
    """Build and run the GUI main loop. Blocks until the window is closed."""
    app = QidLookupApp(initial_db_path=database_path)
    app.mainloop()


def main() -> None:
    """Entry point for the standalone ``qidlookup-gui`` script."""
    launch()


if __name__ == "__main__":
    main()

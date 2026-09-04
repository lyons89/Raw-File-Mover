# RAW File Monitor with MAP Grouping – Multi-Tab Edition
import json
import logging
import os
import re
import shutil
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

CHECK_INTERVAL = 30
SETTINGS_FILE = "monitor_settings.json"
LOG_FILE = "raw_file_monitor.log"
TRANSFER_DB = "transferred_files.json"
AGE_THRESHOLD = timedelta(hours=12)

# Shared lock so concurrent monitors don't race on the transfer DB
_transfer_db_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────────────────────
def build_logger(log_file: str = LOG_FILE) -> logging.Logger:
    logger = logging.getLogger("raw_file_monitor")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.propagate = False
    return logger


# ─────────────────────────────────────────────────────────────────────────────
# FileMonitor  (core logic – unchanged from original)
# ─────────────────────────────────────────────────────────────────────────────
class FileMonitor:
    def __init__(
        self,
        source,
        dest,
        pattern,
        idle_minutes,
        min_size_mb,
        recursive,
        organize_files,
        log_callback,
    ):
        self.source = source
        self.dest = dest
        self.pattern = re.compile(pattern)
        self.idle_time = timedelta(minutes=idle_minutes)
        self.min_size_bytes = min_size_mb * 1024 * 1024
        self.recursive = bool(recursive)
        self.organize_files = organize_files
        self.log = log_callback
        self.running = False
        self._notified = set()
        self.transferred_files = self._load_transferred_files()

    # ── ID helpers ───────────────────────────────────────────────────────────

    def extract_sample_id(self, filename):
        match = re.search(r"((?:MAP|PC)\d+-[^_]+)", filename, re.IGNORECASE)
        return match.group(1) if match else None

    def build_destination_folder(self, sample_id):
        match = re.match(r"([A-Za-z]+)(\d+)", sample_id)
        if not match:
            return None
        prefix = match.group(1).upper()
        number = int(match.group(2))
        start_num = ((number - 1) // 50) * 50 + 1
        end_num = start_num + 49

        if prefix == "MAP":
            project_folder = "Projects_MAP"
            range_folder = f"MAP{start_num:03d}-{end_num:03d}"
        elif prefix == "PC":
            project_folder = "Projects_PC"
            range_folder = f"PC{start_num:03d}-PC{end_num:03d}"
        else:
            project_folder = "Projects"
            range_folder = f"{prefix}{start_num:03d}-{end_num:03d}"

        return os.path.join(
            self.dest, project_folder, range_folder, sample_id, "raw_files"
        )

    # ── Thread control ───────────────────────────────────────────────────────

    def start(self):
        self.running = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()
        self.log("Monitoring started…")

    def stop(self):
        self.running = False
        self.log("Monitoring stopped.")

    def _monitor_loop(self):
        while self.running:
            try:
                self._check_files()
            except Exception as exc:
                self.log(f"Error: {exc}")
            time.sleep(CHECK_INTERVAL)

    # ── File scanning ─────────────────────────────────────────────────────────

    def _iter_source_files(self):
        if not self.recursive:
            for entry in os.scandir(self.source):
                if entry.is_file():
                    yield entry.name, entry.path
        else:
            for root, _, files in os.walk(self.source):
                for name in files:
                    abs_path = os.path.join(root, name)
                    yield os.path.relpath(abs_path, self.source), abs_path

    def _dest_listing(self):
        dest_files = set()
        if os.path.exists(self.dest):
            for root, _, files in os.walk(self.dest):
                for f in files:
                    dest_files.add(f.lower())
        return dest_files

    def _check_files(self):
        now = datetime.now()
        dest_files = self._dest_listing()
        for rel_path, abs_path in self._iter_source_files():
            fname = os.path.basename(rel_path)
            if not self.pattern.match(fname):
                continue
            if self._already_transferred(fname):
                continue
            if fname.lower() in dest_files:
                self.transferred_files.add(fname.lower())
                self._save_transferred_files()
                continue
            try:
                st = os.stat(abs_path)
            except FileNotFoundError:
                continue
            age = now - datetime.fromtimestamp(st.st_mtime)
            if age >= AGE_THRESHOLD or (
                age >= self.idle_time and st.st_size >= self.min_size_bytes
            ):
                self._copy_with_retry(rel_path)

    # ── Copy helpers ──────────────────────────────────────────────────────────

    def _copy_with_retry(self, rel_path):
        for attempt in range(3):
            if self._copy_file(rel_path):
                return
            self.log(f"Retry {attempt + 1} for {rel_path}")
            time.sleep(5)

    def _copy_file(self, rel_path):
        src = os.path.join(self.source, rel_path)
        filename = os.path.basename(rel_path)

        if self.organize_files:
            sample_id = self.extract_sample_id(filename)
            if not sample_id:
                self.log(f"Could not locate project ID in {filename}")
                return False
            dest_folder = self.build_destination_folder(sample_id)
        else:
            dest_folder = self.dest

        os.makedirs(dest_folder, exist_ok=True)
        dst = os.path.join(dest_folder, filename)

        if os.path.exists(dst):
            self.transferred_files.add(filename.lower())
            self._save_transferred_files()
            return True

        try:
            self.log(f"Copying: {filename} → {dest_folder}")
            shutil.copy2(src, dst)
            if os.path.getsize(src) == os.path.getsize(dst):
                self.log(f"✅ Verified: {filename}")
                self.transferred_files.add(filename.lower())
                self._save_transferred_files()
                return True
            return False
        except Exception as exc:
            self.log(f"Error copying {filename}: {exc}")
            return False

    # ── Transfer DB ───────────────────────────────────────────────────────────

    def _load_transferred_files(self) -> set:
        if not os.path.exists(TRANSFER_DB):
            return set()
        try:
            with open(TRANSFER_DB, "r", encoding="utf-8") as fh:
                return set(json.load(fh))
        except Exception as exc:
            self.log(f"Error loading transfer database: {exc}")
            return set()

    def _save_transferred_files(self):
        with _transfer_db_lock:
            # Merge with the on-disk set so concurrent monitors stay in sync
            if os.path.exists(TRANSFER_DB):
                try:
                    with open(TRANSFER_DB, "r", encoding="utf-8") as fh:
                        self.transferred_files |= set(json.load(fh))
                except Exception:
                    pass
            try:
                with open(TRANSFER_DB, "w", encoding="utf-8") as fh:
                    json.dump(sorted(self.transferred_files), fh, indent=2)
            except Exception as exc:
                self.log(f"Error saving transfer database: {exc}")

    def _already_transferred(self, filename: str) -> bool:
        return filename.lower() in self.transferred_files


# ─────────────────────────────────────────────────────────────────────────────
# MonitorTab – one tab = one independent monitor configuration + log
# ─────────────────────────────────────────────────────────────────────────────
class MonitorTab:
    def __init__(
        self,
        notebook: ttk.Notebook,
        tab_number: int,
        logger: logging.Logger,
        save_callback,
    ):
        self.frame = ttk.Frame(notebook)
        self.notebook = notebook
        self.logger = logger
        self.save_callback = save_callback
        self.monitor = None
        self.tab_number = tab_number
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        f = self.frame
        pad = dict(padx=6, pady=3)

        # Row 0 – tab label
        tk.Label(f, text="Tab Name").grid(row=0, column=0, sticky="w", **pad)
        self.tab_name_entry = tk.Entry(f, width=30)
        self.tab_name_entry.grid(row=0, column=1, sticky="w", **pad)
        self.tab_name_entry.insert(0, f"Monitor {self.tab_number}")
        tk.Button(f, text="Rename Tab", command=self._rename_tab).grid(
            row=0, column=2, **pad
        )

        # Row 1 – source
        tk.Label(f, text="Source Folder").grid(row=1, column=0, sticky="w", **pad)
        self.src_entry = tk.Entry(f, width=55)
        self.src_entry.grid(row=1, column=1, **pad)
        tk.Button(f, text="Browse", command=self._browse_src).grid(
            row=1, column=2, **pad
        )

        # Row 2 – destination
        tk.Label(f, text="Destination Folder").grid(row=2, column=0, sticky="w", **pad)
        self.dst_entry = tk.Entry(f, width=55)
        self.dst_entry.grid(row=2, column=1, **pad)
        tk.Button(f, text="Browse", command=self._browse_dst).grid(
            row=2, column=2, **pad
        )

        # Row 3 – regex
        tk.Label(f, text="Regex Filter").grid(row=3, column=0, sticky="w", **pad)
        self.regex_entry = tk.Entry(f, width=55)
        self.regex_entry.grid(row=3, column=1, **pad)
        self.regex_entry.insert(0, r"(?i).*(MAP|PC).*\.raw$")

        # Row 4 – idle time
        tk.Label(f, text="Idle Time (min)").grid(row=4, column=0, sticky="w", **pad)
        self.idle_entry = tk.Entry(f, width=10)
        self.idle_entry.grid(row=4, column=1, sticky="w", **pad)
        self.idle_entry.insert(0, "15")

        # Row 5 – min size
        tk.Label(f, text="Min Size (MB)").grid(row=5, column=0, sticky="w", **pad)
        self.size_entry = tk.Entry(f, width=10)
        self.size_entry.grid(row=5, column=1, sticky="w", **pad)
        self.size_entry.insert(0, "50")

        # Row 6-7 – checkboxes
        self.organize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f, text="Create Sample Folders", variable=self.organize_var
        ).grid(row=6, column=0, columnspan=2, sticky="w", **pad)

        self.recursive_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f, text="Scan subfolders (recursive)", variable=self.recursive_var
        ).grid(row=7, column=0, columnspan=2, sticky="w", **pad)

        # Row 8 – Start/Stop buttons + status label
        btn_row = tk.Frame(f)
        btn_row.grid(row=8, column=0, columnspan=2, sticky="w", pady=5)
        tk.Button(
            btn_row,
            text="▶  Start",
            bg="#2e7d32",
            fg="white",
            width=10,
            command=self._start,
        ).pack(side="left", padx=6)
        tk.Button(
            btn_row,
            text="■  Stop",
            bg="#c62828",
            fg="white",
            width=10,
            command=self._stop,
        ).pack(side="left", padx=6)

        self.status_var = tk.StringVar(value="⏹  Stopped")
        tk.Label(f, textvariable=self.status_var, fg="#c62828").grid(
            row=8, column=2, sticky="e", padx=6
        )

        # Row 9-10 – log box
        tk.Label(f, text="Activity Log:").grid(row=9, column=0, sticky="w", **pad)
        self.log_box = scrolledtext.ScrolledText(f, width=78, height=12)
        self.log_box.grid(row=10, column=0, columnspan=3, padx=6, pady=4)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _rename_tab(self):
        name = self.tab_name_entry.get().strip() or f"Monitor {self.tab_number}"
        self.notebook.tab(self.frame, text=name)
        self.save_callback()

    def _browse_src(self):
        path = filedialog.askdirectory()
        if path:
            self.src_entry.delete(0, tk.END)
            self.src_entry.insert(0, path)

    def _browse_dst(self):
        path = filedialog.askdirectory()
        if path:
            self.dst_entry.delete(0, tk.END)
            self.dst_entry.insert(0, path)

    def log(self, msg: str):
        """Write to the shared rotating log file and this tab's log box."""
        self.logger.info(msg)
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)

    def _start(self):
        if self.monitor and self.monitor.running:
            self.log("Monitor is already running.")
            return
        self.save_callback()
        try:
            self.monitor = FileMonitor(
                self.src_entry.get(),
                self.dst_entry.get(),
                self.regex_entry.get(),
                float(self.idle_entry.get()),
                float(self.size_entry.get()),
                self.recursive_var.get(),
                self.organize_var.get(),
                self.log,
            )
            self.monitor.start()
            self.status_var.set("▶  Running")
            # Prefix the tab label so running tabs are visible at a glance
            name = self.tab_name_entry.get().strip() or f"Monitor {self.tab_number}"
            self.notebook.tab(self.frame, text=f"▶ {name}")
        except Exception as exc:
            self.log(f"Failed to start: {exc}")

    def _stop(self):
        if self.monitor:
            self.monitor.stop()
        self.status_var.set("⏹  Stopped")
        name = self.tab_name_entry.get().strip() or f"Monitor {self.tab_number}"
        self.notebook.tab(self.frame, text=name)

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        return {
            "tab_name": self.tab_name_entry.get(),
            "source": self.src_entry.get(),
            "dest": self.dst_entry.get(),
            "regex": self.regex_entry.get(),
            "idle": self.idle_entry.get(),
            "size": self.size_entry.get(),
            "recursive": self.recursive_var.get(),
            "organize": self.organize_var.get(),
        }

    def load_settings(self, s: dict):
        name = s.get("tab_name", f"Monitor {self.tab_number}")
        self.tab_name_entry.delete(0, tk.END)
        self.tab_name_entry.insert(0, name)
        self.notebook.tab(self.frame, text=name)

        for widget, key, default in [
            (self.src_entry, "source", ""),
            (self.dst_entry, "dest", ""),
            (self.regex_entry, "regex", r"(?i).*(MAP|PC).*\.raw$"),
            (self.idle_entry, "idle", "15"),
            (self.size_entry, "size", "50"),
        ]:
            widget.delete(0, tk.END)
            widget.insert(0, s.get(key, default))

        self.recursive_var.set(bool(s.get("recursive", False)))
        self.organize_var.set(bool(s.get("organize", True)))


# ─────────────────────────────────────────────────────────────────────────────
# App – manages the notebook and tab lifecycle
# ─────────────────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("RAW File Monitor")
        root.minsize(700, 600)
        self.logger = build_logger(LOG_FILE)
        self.tabs: list[MonitorTab] = []
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self.root, bd=1, relief="raised")
        toolbar.pack(fill="x", side="top")
        tk.Button(toolbar, text="＋  Add Monitor", command=self._add_tab).pack(
            side="left", padx=4, pady=3
        )
        tk.Button(toolbar, text="✕  Remove Tab", command=self._remove_tab).pack(
            side="left", padx=4, pady=3
        )

        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=4, pady=4)

    # ── Tab management ────────────────────────────────────────────────────────

    def _add_tab(self, settings: dict = None) -> MonitorTab:
        tab_num = len(self.tabs) + 1
        tab = MonitorTab(self.notebook, tab_num, self.logger, self._save_settings)
        self.notebook.add(tab.frame, text=f"Monitor {tab_num}")
        self.tabs.append(tab)
        if settings:
            tab.load_settings(settings)
        self.notebook.select(tab.frame)
        return tab

    def _remove_tab(self):
        if len(self.tabs) <= 1:
            self.logger.warning("Cannot remove the only remaining tab.")
            return
        idx = self.notebook.index(self.notebook.select())
        self.tabs[idx]._stop()  # gracefully stop any running monitor
        self.notebook.forget(idx)
        self.tabs.pop(idx)
        self._save_settings()

    # ── Settings persistence ──────────────────────────────────────────────────

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump([t.get_settings() for t in self.tabs], fh, indent=2)
        except Exception as exc:
            self.logger.error(f"Error saving settings: {exc}")

    def _load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            self._add_tab()
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Backward-compat: old single-dict format → wrap in a list
            if isinstance(data, dict):
                data = [data]
            for s in data:
                self._add_tab(settings=s)
        except Exception as exc:
            self.logger.error(f"Error loading settings: {exc}")
            self._add_tab()
        if not self.tabs:
            self._add_tab()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()

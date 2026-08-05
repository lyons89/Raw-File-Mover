# RAW File Monitor with MAP Grouping
import os
import time
import threading
import shutil
import re
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import filedialog, scrolledtext
import pystray
from PIL import Image, ImageDraw

CHECK_INTERVAL = 30
SETTINGS_FILE = "monitor_settings.json"
LOG_FILE = "raw_file_monitor.log"
AGE_THRESHOLD = timedelta(hours=12)


def build_logger(log_file: str = LOG_FILE) -> logging.Logger:
    logger = logging.getLogger("raw_file_monitor")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.propagate = False
    return logger


class FileMonitor:
    def __init__(self, source, dest, pattern, idle_minutes, min_size_mb, recursive, organize_files, log_callback):
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

    def extract_sample_id(self, filename):

        match = re.search(
            r'((?:MAP|PC)\d+-[^_]+)',
            filename,
            re.IGNORECASE
        )

        if match:
            return match.group(1)

        return None
    def build_destination_folder(self, sample_id):

        match = re.match(
            r'([A-Za-z]+)(\d+)',
            sample_id
        )

        if not match:
            return None

        prefix = match.group(1).upper()
        number = int(match.group(2))

        start_num = ((number - 1) // 50) * 50 + 1
        end_num = start_num + 49

        #
        # MAP projects
        #
        if prefix == "MAP":

            project_folder = "Projects MAP"

            range_folder = (
                f"MAP{start_num:03d}-{end_num:03d}"
            )

        #
        # PC projects
        #
        elif prefix == "PC":

            project_folder = "Projects PC"

            range_folder = (
                f"PC{start_num:03d}-PC{end_num:03d}"
            )

        #
        # fallback
        #
        else:

            project_folder = "Projects"

            range_folder = (
                f"{prefix}{start_num:03d}-{end_num:03d}"
            )

        return os.path.join(
            self.dest,
            project_folder,
            range_folder,
            sample_id,
            "raw_files"
        )    

    def start(self):
        self.running = True
        threading.Thread(target=self.monitor_loop, daemon=True).start()
        self.log('Monitoring started...')

    def stop(self):
        self.running = False
        self.log('Monitoring stopped.')

    def monitor_loop(self):
        while self.running:
            try:
                self.check_files()
            except Exception as e:
                self.log(f'Error: {e}')
            time.sleep(CHECK_INTERVAL)

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

    def check_files(self):
        now = datetime.now()
        dest_files = self._dest_listing()
        for rel_path, abs_path in self._iter_source_files():
            fname = os.path.basename(rel_path)
            if not self.pattern.match(fname):
                continue
            if fname.lower() in dest_files:
                continue
            try:
                st = os.stat(abs_path)
            except FileNotFoundError:
                continue
            age = now - datetime.fromtimestamp(st.st_mtime)
            if age >= AGE_THRESHOLD or (age >= self.idle_time and st.st_size >= self.min_size_bytes):
                self.copy_with_retry(rel_path)

    def copy_with_retry(self, rel_path):
        for attempt in range(3):
            if self.copy_file(rel_path):
                return
            self.log(f'Retry {attempt+1} for {rel_path}')
            time.sleep(5)

    def copy_file(self, rel_path):
        src = os.path.join(self.source, rel_path)
        filename = os.path.basename(rel_path)
        sample_id = None

        if self.organize_files:
            sample_id = self.extract_sample_id(filename)

            if not sample_id:
                self.log(
                    f'Could not locate project ID in {filename}'
                )
                return False        
        if self.organize_files:
            dest_folder = self.build_destination_folder(sample_id)
        else:
            dest_folder = self.dest        
        os.makedirs(dest_folder, exist_ok=True)
        dst = os.path.join(dest_folder, filename)
        if os.path.exists(dst):
            return True
        try:
            self.log(f'Copying: {filename} -> {dest_folder}')
            shutil.copy2(src, dst)
            if os.path.getsize(src) == os.path.getsize(dst):
                self.log(f'✅ Verified: {filename}')
                return True
            return False
        except Exception as e:
            self.log(f'Error copying {filename}: {e}')
            return False


class App:
    def __init__(self, root):
        self.root = root
        root.title('RAW File Monitor')
        self.logger = build_logger(LOG_FILE)
        self.monitor = None
        self.create_ui()
        self.load_settings()

    def create_ui(self):
        tk.Label(self.root,text='Source Folder').grid(row=0,column=0,sticky='w')
        self.src_entry=tk.Entry(self.root,width=50); self.src_entry.grid(row=0,column=1)
        tk.Button(self.root,text='Browse',command=self.browse_src).grid(row=0,column=2)
        tk.Label(self.root,text='Destination Folder').grid(row=1,column=0,sticky='w')
        self.dst_entry=tk.Entry(self.root,width=50); self.dst_entry.grid(row=1,column=1)
        tk.Button(self.root,text='Browse',command=self.browse_dst).grid(row=1,column=2)
        tk.Label(self.root,text='Regex Filter').grid(row=2,column=0,sticky='w')
        self.regex_entry=tk.Entry(self.root,width=50); self.regex_entry.grid(row=2,column=1)
        tk.Label(self.root,text='Idle Time (min)').grid(row=3,column=0,sticky='w')
        self.idle_entry=tk.Entry(self.root); self.idle_entry.grid(row=4,column=1,sticky='w')
        tk.Label(self.root,text='Min Size (MB)').grid(row=5,column=0,sticky='w')
        self.size_entry=tk.Entry(self.root); self.size_entry.grid(row=5,column=1,sticky='w')
        self.recursive_var=tk.BooleanVar(value=False)
        self.organize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.root,
            text="Create Sample Folders",
            variable=self.organize_var
        ).grid(row=6, column=0, columnspan=2, sticky='w')
        tk.Checkbutton(self.root,text='Scan subfolders (recursive)',variable=self.recursive_var).grid(row=8,column=0,columnspan=2,sticky='w')
        tk.Button(self.root,text='Start',command=self.start_monitor).grid(row=7,column=0)
        tk.Button(self.root,text='Stop',command=self.stop_monitor).grid(row=7,column=1)
        self.log_box=scrolledtext.ScrolledText(self.root,width=70,height=15)
        self.log_box.grid(row=8,column=0,columnspan=3)

    def browse_src(self):
        f=filedialog.askdirectory()
        if f: self.src_entry.delete(0,tk.END); self.src_entry.insert(0,f)
    def browse_dst(self):
        f=filedialog.askdirectory()
        if f: self.dst_entry.delete(0,tk.END); self.dst_entry.insert(0,f)
    def log(self,msg):
        self.logger.info(msg)
        self.log_box.insert(tk.END,msg+'\n')
        self.log_box.see(tk.END)
    def start_monitor(self):
        self.save_settings()
        self.monitor=FileMonitor(self.src_entry.get(),self.dst_entry.get(),self.regex_entry.get(),float(self.idle_entry.get()),float(self.size_entry.get()),self.recursive_var.get(),self.organize_var.get(),self.log)
        self.monitor.start()
    def stop_monitor(self):
        if self.monitor: self.monitor.stop()
    def save_settings(self):
        json.dump({'source':self.src_entry.get(),'dest':self.dst_entry.get(),'regex':self.regex_entry.get(),'idle':self.idle_entry.get(),'size':self.size_entry.get(),'recursive':self.recursive_var.get(),'organize':self.organize_var.get(),},open(SETTINGS_FILE,'w'))
    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            self.regex_entry.insert(0,r'(?i).*(MAP|PC).*\.raw$')
            self.idle_entry.insert(0,'15')
            self.size_entry.insert(0,'50')
            self.organize_var.set(True)
            return
        s=json.load(open(SETTINGS_FILE))
        self.src_entry.insert(0,s.get('source',''))
        self.dst_entry.insert(0,s.get('dest',''))
        self.regex_entry.insert(0,s.get('regex',r'(?i).*(MAP|PC).*\.raw$'))
        self.idle_entry.insert(0,s.get('idle','15'))
        self.size_entry.insert(0,s.get('size','50'))
        
        self.organize_var.set(
            bool(s.get("organize", True))
        )

if __name__=='__main__':
    root=tk.Tk()
    App(root)
    root.mainloop()

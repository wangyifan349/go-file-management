#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import shutil
import threading
import hashlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from typing import List, Tuple, Dict
# -------------------------------------------------------------------
#   Supported extensions
# -------------------------------------------------------------------
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.m4v', '.webm'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a'}
# -------------------------------------------------------------------
#   Utility functions
# -------------------------------------------------------------------
def compute_sha256(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file in streaming mode."""
    hasher = hashlib.sha256()
    with file_path.open('rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
def is_image(file_path: Path) -> bool:
    return file_path.suffix.lower() in IMAGE_EXTENSIONS
def is_video(file_path: Path) -> bool:
    return file_path.suffix.lower() in VIDEO_EXTENSIONS
def is_audio(file_path: Path) -> bool:
    return file_path.suffix.lower() in AUDIO_EXTENSIONS
def get_unique_path(target_path: Path) -> Path:
    """
    If target_path exists, append _1, _2, ... until we find a non-existing path.
    """
    if not target_path.exists():
        return target_path
    parent = target_path.parent
    stem = target_path.stem
    suffix = target_path.suffix
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
def safe_move_or_copy(src: Path, dst: Path, do_copy: bool) -> Path:
    """
    Move or copy src -> dst, avoiding overwrite by getting a unique path.
    Returns the final path.
    """
    final_dst = get_unique_path(dst)
    if do_copy:
        shutil.copy2(str(src), str(final_dst))
    else:
        shutil.move(str(src), str(final_dst))
    return final_dst
# -------------------------------------------------------------------
#   Core logic functions
# -------------------------------------------------------------------
def scan_sources(
        source_dirs: List[Path],
        log_widget: scrolledtext.ScrolledText
    ) -> List[Tuple[Path, str, int, str]]:
    """
    Walk all source_dirs, find supported media files, compute size & sha256.
    Returns a list of tuples: (file_path, media_type, size_bytes, sha256).
    """
    entries: List[Tuple[Path, str, int, str]] = []
    log("Starting pre-scan...", log_widget)
    for src_dir in source_dirs:
        if not src_dir.is_dir():
            log(f"Skipping invalid source: {src_dir}", log_widget)
            continue
        for root, _, files in os.walk(src_dir):
            for filename in files:
                file_path = Path(root) / filename
                if is_image(file_path):
                    media_type = 'image'
                elif is_video(file_path):
                    media_type = 'video'
                elif is_audio(file_path):
                    media_type = 'audio'
                else:
                    continue
                try:
                    size = file_path.stat().st_size
                    file_hash = compute_sha256(file_path)
                    entries.append((file_path, media_type, size, file_hash))
                except Exception as e:
                    log(f"Warning: cannot process {file_path}: {e}", log_widget)
    # summary
    counts = {'image': 0, 'video': 0, 'audio': 0}
    total_bytes = 0
    for _, mtype, size, _ in entries:
        counts[mtype] += 1
        total_bytes += size
    mb = total_bytes / (1024 ** 2)
    log(f"Found {counts['image']} images, "
        f"{counts['video']} videos, {counts['audio']} audio, "
        f"{mb:.2f} MB total.", log_widget)
    return entries
def move_or_copy_entries(
        entries: List[Tuple[Path, str, int, str]],
        destination: Path,
        do_copy: bool,
        log_widget: scrolledtext.ScrolledText
    ):
    """
    Perform move or copy of all entries under destination/images, /videos, /audio
    """
    folders = {
        'image': destination / 'images',
        'video': destination / 'videos',
        'audio': destination / 'audio'
    }
    for fld in folders.values():
        fld.mkdir(parents=True, exist_ok=True)
    action = "Copying" if do_copy else "Moving"
    log(f"{action} files...", log_widget)
    for src_path, media_type, _, _ in entries:
        target_folder = folders[media_type]
        desired = target_folder / src_path.name
        try:
            final_path = safe_move_or_copy(src_path, desired, do_copy)
            log(f"  {action[:-3]}d {src_path} -> {final_path}", log_widget)
        except Exception as e:
            log(f"Error processing {src_path}: {e}", log_widget)
def deduplicate_folder(
        folder: Path,
        log_widget: scrolledtext.ScrolledText
    ):
    """
    Remove duplicate files in folder (and subfolders) by SHA-256.
    Keeps first encountered copy.
    """
    log(f"Deduplicating in {folder}...", log_widget)
    seen_hashes: Dict[str, Path] = {}
    for root, _, files in os.walk(folder):
        for name in files:
            path = Path(root) / name
            try:
                h = compute_sha256(path)
            except Exception as e:
                log(f"Warning: cannot hash {path}: {e}", log_widget)
                continue
            if h in seen_hashes:
                original = seen_hashes[h]
                try:
                    path.unlink()
                    log(f"  Deleted duplicate {path} (original: {original})", log_widget)
                except Exception as e:
                    log(f"Error deleting {path}: {e}", log_widget)
            else:
                seen_hashes[h] = path
# -------------------------------------------------------------------
#   Logging helper (thread-safe)
# -------------------------------------------------------------------
def log(message: str, text_widget: scrolledtext.ScrolledText):
    def append():
        text_widget.configure(state='normal')
        text_widget.insert(tk.END, message + '\n')
        text_widget.see(tk.END)
        text_widget.configure(state='disabled')
    text_widget.after(0, append)
# -------------------------------------------------------------------
#   Worker thread
# -------------------------------------------------------------------
def worker_thread(
        source_dirs: List[Path],
        destination: Path,
        do_copy: bool,
        do_dedupe: bool,
        log_widget: scrolledtext.ScrolledText,
        start_button: ttk.Button
    ):
    try:
        entries = scan_sources(source_dirs, log_widget)
        if not entries:
            log("No media files found. Aborting.", log_widget)
            return
        move_or_copy_entries(entries, destination, do_copy, log_widget)
        if do_dedupe:
            for sub in ('images', 'videos', 'audio'):
                deduplicate_folder(destination / sub, log_widget)
        log(f"All done! Files are under {destination.resolve()}", log_widget)
    finally:
        # re-enable start button
        def enable():
            start_button.configure(state='normal')
        log_widget.after(0, enable)
# -------------------------------------------------------------------
#   GUI class
# -------------------------------------------------------------------
class MediaMoverApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Media Mover & Deduper")
        # --- Source frame ---
        src_frame = ttk.LabelFrame(root, text="Source Folders")
        src_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.source_list = tk.Listbox(src_frame, height=4)
        self.source_list.pack(side="left", fill="both", expand=True, padx=(5,0), pady=5)
        scroll = ttk.Scrollbar(src_frame, orient="vertical", command=self.source_list.yview)
        scroll.pack(side="left", fill="y", pady=5)
        self.source_list.configure(yscrollcommand=scroll.set)
        btn_src = ttk.Frame(src_frame)
        btn_src.pack(side="left", padx=5, pady=5)
        ttk.Button(btn_src, text="Add", command=self.add_source).pack(fill="x", pady=(0,5))
        ttk.Button(btn_src, text="Remove", command=self.remove_source).pack(fill="x")
        # --- Destination frame ---
        dst_frame = ttk.LabelFrame(root, text="Destination Folder")
        dst_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.dest_var = tk.StringVar()
        ttk.Entry(dst_frame, textvariable=self.dest_var, width=40).pack(side="left", fill="x", expand=True, padx=5, pady=5)
        ttk.Button(dst_frame, text="Browse", command=self.choose_destination).pack(side="left", padx=5)
        # --- Options frame ---
        opt_frame = ttk.Frame(root)
        opt_frame.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.copy_var = tk.BooleanVar(value=False)
        ttk.Radiobutton(opt_frame, text="Move files", variable=self.copy_var, value=False).pack(side="left", padx=(0,10))
        ttk.Radiobutton(opt_frame, text="Copy files", variable=self.copy_var, value=True).pack(side="left", padx=(0,20))
        self.dedupe_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Auto dedupe", variable=self.dedupe_var).pack(side="left")
        # --- Log area ---
        log_frame = ttk.LabelFrame(root, text="Log")
        log_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        root.grid_rowconfigure(3, weight=1)
        root.grid_columnconfigure(0, weight=1)
        self.log_widget = scrolledtext.ScrolledText(log_frame, state="disabled", height=15)
        self.log_widget.pack(fill="both", expand=True, padx=5, pady=5)
        # --- Start button ---
        self.start_button = ttk.Button(root, text="Start", command=self.on_start)
        self.start_button.grid(row=4, column=0, pady=(0,10))
    def add_source(self):
        folder = filedialog.askdirectory(title="Select Source Folder")
        if folder:
            self.source_list.insert(tk.END, folder)
    def remove_source(self):
        for idx in reversed(self.source_list.curselection()):
            self.source_list.delete(idx)
    def choose_destination(self):
        folder = filedialog.askdirectory(title="Select Destination Folder")
        if folder:
            self.dest_var.set(folder)
    def on_start(self):
        # gather inputs
        sources = [Path(p).expanduser() for p in self.source_list.get(0, tk.END)]
        dest = self.dest_var.get().strip()
        do_copy = self.copy_var.get()
        do_dedupe = self.dedupe_var.get()
        # validation
        if not sources:
            messagebox.showwarning("Warning", "Please add at least one source folder.")
            return
        if not dest:
            messagebox.showwarning("Warning", "Please select a destination folder.")
            return
        destination = Path(dest).expanduser()
        destination.mkdir(parents=True, exist_ok=True)
        # disable Start
        self.start_button.configure(state="disabled")
        # clear log
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state="disabled")
        # start worker
        thread = threading.Thread(
            target=worker_thread,
            args=(sources, destination, do_copy, do_dedupe, self.log_widget, self.start_button),
            daemon=True
        )
        thread.start()
# -------------------------------------------------------------------
#   Entry point
# -------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = MediaMoverApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

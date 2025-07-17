#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, shutil, hashlib
from pathlib import Path
from typing import List, Tuple, Dict

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.m4v', '.webm'}

def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS

def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS

def compute_sha256(path: Path, chunk_size: int = 8192) -> str:
    hasher = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()

def pre_scan(sources: List[Path]) -> List[Tuple[Path,str,int,str]]:
    entries: List[Tuple[Path,str,int,str]] = []
    print("Pre-scan: counting files and computing SHA-256 hashes...")
    for src in sources:
        if not src.is_dir():
            print(f"Skip invalid dir: {src}")
            continue
        for root, _, files in os.walk(src):
            for name in files:
                p = Path(root) / name
                if is_image(p): t='image'
                elif is_video(p): t='video'
                else: continue
                try:
                    size = p.stat().st_size
                    h = compute_sha256(p)
                    entries.append((p, t, size, h))
                except Exception as e:
                    print(f"Warn: cannot process {p}: {e}")
    img_count = sum(1 for e in entries if e[1]=='image')
    vid_count = sum(1 for e in entries if e[1]=='video')
    total_mb = sum(e[2] for e in entries) / 1024**2
    print(f"Found {img_count} images, {vid_count} videos, total {total_mb:.2f} MB")
    return entries

def unique_target(dest: Path) -> Path:
    if not dest.exists(): return dest
    parent, stem, suf = dest.parent, dest.stem, dest.suffix
    i = 1
    while True:
        new = parent / f"{stem}_{i}{suf}"
        if not new.exists(): return new
        i += 1

def move_entries(entries: List[Tuple[Path,str,int,str]], dest: Path) -> None:
    img_dir, vid_dir = dest/'images', dest/'videos'
    img_dir.mkdir(parents=True, exist_ok=True)
    vid_dir.mkdir(parents=True, exist_ok=True)
    print("Moving files...")
    for p, t, _, _ in entries:
        target = img_dir/p.name if t=='image' else vid_dir/p.name
        tgt = unique_target(target)
        try:
            shutil.move(str(p), str(tgt))
            print(f"Moved {p} -> {tgt}")
        except Exception as e:
            print(f"Error moving {p}: {e}")

def dedupe(folder: Path) -> None:
    print(f"Deduping in {folder} by SHA-256...")
    seen: Dict[str,Path] = {}
    for root, _, files in os.walk(folder):
        for name in files:
            p = Path(root)/name
            try:
                h = compute_sha256(p)
            except Exception as e:
                print(f"Warn: cannot hash {p}: {e}"); continue
            if h in seen:
                print(f"Deleting duplicate {p} (same as {seen[h]})")
                try: p.unlink()
                except Exception as e: print(f"Error deleting {p}: {e}")
            else:
                seen[h] = p

def main():
    print("Media Mover & Deduper")
    sources: List[Path] = []
    print("Enter source dirs (empty line to finish):")
    while True:
        line = input("Src dir: ").strip()
        if not line: break
        sources.append(Path(line).expanduser())
    if not sources:
        print("No sources; exit."); return
    dest = Path(input("Enter dest dir: ").strip()).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    entries = pre_scan(sources)
    if input("Proceed? (y/n): ").strip().lower()!='y':
        print("Cancelled"); return
    move_entries(entries, dest)
    dedupe(dest/'images'); dedupe(dest/'videos')
    print("Done. Destination:", dest)

if __name__ == "__main__":
    main()

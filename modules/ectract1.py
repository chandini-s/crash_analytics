"""
Extract the latest downloaded bugreport and recursively expand any nested archives.

- Wipes ./extracted_bugreports on every run (saves disk space)
- Extracts newest ZIP from ./downloaded_bugreports
- Recursively extracts inner archives (zip/7z/mar/tar/tgz/gz) next to themselves
- Avoids re-extracting folders already present
- Adds a small safeguard for very long Windows paths
- Searches bugreport-*.txt for "DUMP OF SERVICE diskstats"
"""

from __future__ import annotations

import os
import glob
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Iterable, List

# ---------- Paths & constants ----------

# project_root = <repo> (because this file lives in <repo>/modules/extraction.py)
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]

DOWNLOAD_DIR: Path = PROJECT_ROOT / "downloaded_bugreports"
EXTRACT_ROOT: Path = PROJECT_ROOT / "extracted_bugreports"  # wiped each run
SEVEN_ZIP = r"C:\Program Files\7-Zip\7z.exe"  # change if custom

SEARCH_PREFIX = "bugreport-"
SEARCH_STRING = "DUMP OF SERVICE diskstats"

# how many recursive passes to attempt for nested archives
MAX_ROUNDS = 4
# treat these as archives (case-insensitive)
ARCHIVE_EXTS = {".zip", ".7z", ".mar", ".tar", ".tgz", ".gz"}


# ---------- Helpers ----------

def _path_ok(p: Path) -> Path:
    """Trim folder name if Windows path is getting too long."""
    s = str(p)
    if len(s) <= 230:
        return p
    # shorten final folder name; keep parent the same
    return p.parent / (p.name[:80] or "x")


def run_checked(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}")


def extract_with_7zip(archive: Path, out_dir: Path) -> None:
    """Extract using 7-Zip when available, otherwise fall back for .zip only."""
    out_dir = _path_ok(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if Path(SEVEN_ZIP).exists():
        # 7z handles zip/7z/tar/gz and many more; -y = yes to all prompts
        run_checked([SEVEN_ZIP, "x", "-y", str(archive), f"-o{out_dir}"])
        return

    # Fallback for plain .zip if 7z isn't installed
    if archive.suffix.lower() == ".zip":
        shutil.unpack_archive(str(archive), str(out_dir))
        return

    raise RuntimeError(
        f"Cannot extract {archive.name} without 7-Zip installed. "
        f"Install 7-Zip or set SEVEN_ZIP to its path."
    )


# ---------- Core flow ----------

def get_latest_bugreport_zip() -> Path | None:
    """Return newest 'debugarchive_*.zip' inside DOWNLOAD_DIR, or None."""
    files = glob.glob(str(DOWNLOAD_DIR / "debugarchive_*.zip"))
    if not files:
        print("No bugreport ZIP files found in downloaded_bugreports.")
        return None
    latest = max(files, key=os.path.getmtime)
    print(f"Latest bugreport found: {latest}")
    return Path(latest)


def reset_extract_root() -> Path:
    """Delete EXTRACT_ROOT and recreate it empty."""
    if EXTRACT_ROOT.exists():
        shutil.rmtree(EXTRACT_ROOT, ignore_errors=True)
    EXTRACT_ROOT.mkdir(parents=True, exist_ok=True)
    return EXTRACT_ROOT


def extract_top_level(latest_zip: Path) -> Path:
    """Extract the top-level zip into EXTRACT_ROOT and return that path."""
    # optional per-run subdir; comment the next 2 lines if you prefer a flat root
    run_dir = EXTRACT_ROOT / datetime.now().strftime("extract_%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    print("Extracting top-level with 7-Zip...")
    extract_with_7zip(latest_zip, run_dir)
    print("Extracted.")
    return run_dir


def extract_all_nested_archives(root_dir: Path, *, max_rounds: int = MAX_ROUNDS) -> bool:
    """
    Recursively expand inner archives under root_dir.

    Each archive is extracted next to itself in a sibling folder named after the archive's stem.
    We avoid re-extracting if that folder already exists. Returns True if any extraction happened.
    """
    root_dir = Path(root_dir)
    extracted_any = False

    for _ in range(max_rounds):
        did_round = False
        # Find archives that still exist (case-insensitive suffix check)
        archives: List[Path] = [
            p for p in root_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in ARCHIVE_EXTS
        ]

        for arc in archives:
            out_dir = _path_ok(arc.parent / arc.stem)
            if out_dir.exists():
                continue  # already expanded

            try:
                print(f"Extracting nested: {arc}")
                extract_with_7zip(arc, out_dir)
                did_round = True
                extracted_any = True
                print("Extracted")
            except Exception as e:
                # continue rather than abort the whole run
                print(f"Exception while extracting '{arc.name}': {e}")

        if not did_round:
            break

    return extracted_any


def find_text_files_with(prefix: str, root_dir: Path) -> Iterable[Path]:
    """Yield files under root_dir whose names start with prefix and end in .txt."""
    for p in root_dir.rglob(f"{prefix}*.txt"):
        if p.is_file():
            yield p


def search_diskstats(root_dir: Path) -> None:
    """Search bugreport-*.txt for the diskstats marker."""
    print(f"Searching for '{SEARCH_STRING}' in files starting with '{SEARCH_PREFIX}'...")
    any_found = False
    for p in find_text_files_with(SEARCH_PREFIX, root_dir):
        try:
            text = p.read_text(errors="ignore")
        except Exception as e:
            print(f"Error reading {p}: {e}")
            continue
        if SEARCH_STRING in text:
            print(f"FOUND in: {p}")
            any_found = True

    if not any_found:
        print(f"'{SEARCH_STRING}' not found in any '{SEARCH_PREFIX}*.txt' files.")


# ---------- CLI entry ----------

def dump_event_main() -> None:
    latest_zip = get_latest_bugreport_zip()
    if not latest_zip:
        return

    reset_extract_root()  # wipe previous runs
    top = extract_top_level(latest_zip)
    print("Extracting nested zip files using 7-Zip...")
    extract_all_nested_archives(top)
    print("Nested extraction complete.")

    # Optional: also look in the whole EXTRACT_ROOT if you want
    search_diskstats(top)
    print("Extraction and search completed.")


if __name__ == "__main__":
    dump_event_main()

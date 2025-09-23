""" This script automates the extraction of the latest bugreport ZIP file from the Downloads directory, using 7-Zip for extraction.
It recursively extracts any nested ZIP files and searches for specific like camera-related text files and DUMP OF SERVICE event."""

import os
import glob
import subprocess
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DOWNLOAD_DIR = ROOT.parent / "downloaded_bugreports"
EXTRACT_DIR = ROOT.parent / "extracted_bugreports"
SEVEN_ZIP = os.environ.get("SEVEN_ZIP",r"C:\Program Files\7-Zip\7z.exe")
SEARCH_PREFIX = "bugreport-"
SEARCH_STRING = "DUMP OF SERVICE diskstats"


def get_latest_bugreport_zip():
    files = glob.glob(os.path.join(DOWNLOAD_DIR, "debugarchive_*.zip"))
    if not files:
        print("No bugreport ZIP files found in Downloads.")
        return None
    latest_file = max(files, key=os.path.getctime)
    print(f"Latest bugreport found: {latest_file}")
    return latest_file


def extract_with_7zip(zip_path, extract_to):
    try:
        os.makedirs(extract_to, exist_ok=True)
        print(f"Extracting with 7-Zip")
        result = subprocess.run([SEVEN_ZIP, 'x', '-y', zip_path, f"-o{extract_to}"],
                        capture_output=True, text=True)
        if result.returncode != 0:
            print(f"7-Zip failed: \n{result.stderr}")
        else:
            print(f"Extracted ")
    except Exception as e:
            print(f"Exception while extracting: {e}")


def extract_all_nested_zips(root_dir):
    extracted_any = False
    for dirpath, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".zip"):
                zip_path = os.path.join(dirpath, file)
                extract_to = os.path.join(dirpath, f"extracted_{os.path.splitext(file)[0]}")
                if not os.path.exists(extract_to):  # avoid re-extract
                    extract_with_7zip(zip_path, extract_to)
                    extracted_any = True
    return extracted_any


def find_camera_txt_files(root_dir):
    print(f"Searching for camera txt files in ...")
    found_files = []
    for dirpath, _, files in os.walk(root_dir):
        for file in files:
            if file.startswith("cameraserver") and file.endswith(".txt"):
                found_files.append(os.path.join(dirpath, file))
    return found_files


def search_string_in_prefixed_file(root_dir, prefix, search_string):
    print(f"Searching for '{search_string}' in files starting with '{prefix}'...")
    found = False
    for dirpath, _, files in os.walk(root_dir):
        for file in files:
            if file.startswith(prefix) and file.endswith(".txt"):
                file_path = os.path.join(dirpath, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if search_string in line:
                                print(f"Found '{search_string}'")
                                found = True
                                return search_string
                except Exception as e:
                    print(f"Error reading: {e}")
    if not found:
        print(f"'{search_string}' not found in any '{prefix}*.txt' files.")


def clean_and_prepare_extract_dir():
    if os.path.exists(EXTRACT_DIR):
        shutil.rmtree(EXTRACT_DIR)
    os.makedirs(EXTRACT_DIR)


def camera_txt_main():
    zip_path =  get_latest_bugreport_zip()
    if not zip_path:
        return
    clean_and_prepare_extract_dir()
    # Step 1: Extract main zip
    extract_with_7zip(zip_path, EXTRACT_DIR)
    # Step 2: Recursively extract nested zips
    print("Extracting nested zip files using 7-Zip...")
    while extract_all_nested_zips(EXTRACT_DIR):
        pass  # Keep extracting until no zip files remain
    # Step 3: Find camera*.txt files
    camera_txt_files = find_camera_txt_files(EXTRACT_DIR)
    if camera_txt_files:
        print("Found camera txt files:")
        for f in camera_txt_files:
            print("   -", f)
    else:
        print("No camera txt files found.")


def dump_event_main():
    zip_path = get_latest_bugreport_zip()
    if not zip_path:
        return

    clean_and_prepare_extract_dir()

    # Step 1: Extract main zip
    extract_with_7zip(zip_path, EXTRACT_DIR)

    # Step 2: Recursively extract nested zips
    print("Extracting nested zip files using 7-Zip...")
    while extract_all_nested_zips(EXTRACT_DIR):
        pass  # Keep extracting until no zip files remain

    # Step 3: Search for specific string in target txt files
    search_string = search_string_in_prefixed_file(EXTRACT_DIR, SEARCH_PREFIX, SEARCH_STRING)
    return search_string
if __name__ == "__main__":
    dump_event_main()
    print("Extraction and search completed.")



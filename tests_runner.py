""" Run tests with pytest and generate HTML and JUnit reports. """

from __future__ import annotations
import os
from pathlib import Path
import pytest
from utils import get_focused_app, get_serial_number, get_product_details,get_selected_device


ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"

def _reports_dir() -> Path:
    rd = os.getenv("REPORTS_DIR")
    if rd: return Path(rd)
    ws = os.getenv("WORKSPACE")
    if ws: return Path(ws) / "reports"
    return Path(__file__).resolve().parent / "reports"

def _pick_target_by_focus(focused: str) -> str:
    focused_app = (focused or "").lower()
    if "zoom" in focused_app:
        return "testcases/tests_zoom.py"
    if "teams" in focused_app:
        return "testcases/tests_mtr.py"
    if "frogger" in focused_app:
        return "testcases/tests_device_mode.py"
    return "testcases"

def main() -> int:
    device = get_selected_device()
    os.environ.pop("JAVA_HOME", None) # avoid leaking env to pytest-html
    os.environ.pop("WORKSPACE", None)
    os.environ.pop("GIT_URL", None)

    # selector for adb utils (use ip:port if only IP is given)
    selector = device if ":" in device else f"{device}:5555"
    serial = get_serial_number(selector) or selector
    board, display = get_product_details(selector)
    focused = get_focused_app(selector)
    print(f"Selected device: {serial} | {board} / {display}")
    print(f"Focused app: {focused}")
    target = _pick_target_by_focus(focused)
    print(f"Running test target: {target} (based on focused app)")
    REPORTS_DIR = _reports_dir()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE = os.getenv("REPORT_FILE","index.html")
    html = (REPORTS_DIR / REPORT_FILE).resolve()
    junit_xml = (REPORTS_DIR / "results.xml").resolve()
    args = [
        target,
        "-q",
        "--disable-warnings",
        "--html", str(html),
        "--self-contained-html",
        f"--junit-xml={junit_xml}",
    ]
    return pytest.main(args)


if __name__ == "__main__":
    """ Entry point for running tests with pytest. """
    raise SystemExit(main())
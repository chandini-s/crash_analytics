from __future__ import annotations
import os, sys, re, datetime as dt
from pathlib import Path
import pytest

# --- your existing helpers (already in your repo) ---
from utils import get_focused_app, get_serial_number, get_product_details

# ----------------------------------------------------

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"


def _device_from_env() -> str:
    dev = (os.getenv("DEVICE") or "").strip()
    if dev:
        return dev
    devs = (os.getenv("DEVICES") or "").strip()
    if devs:
        first = [p.strip() for p in re.split(r"[ ,;]+", devs) if p.strip()]
        if first:
            return first[0]
    raise SystemExit("ERROR: DEVICE/DEVICES not set in Jenkins parameters.")


def _pick_target_by_focus(focused: str) -> str:
    f = (focused or "").lower()
    if "zoom" in f:
        return "testcases/tests_zoom"
    if "teams" in f:
        return "testcases/tests_mtr"
    if "oobe" in f or "settings" in f:
        return "testcases/tests_oobe"
    return "testcases/tests_device_mode"

def pytest_configure(config):
    """Remove unwanted environment metadata from pytest-html report"""
    metadata = getattr(config, "_metadata", {})
    for key in ["JAVA_HOME", "WORKSPACE", "GIT_URL"]:
        metadata.pop(key, None)

def main() -> int:
    device = _device_from_env()

    # selector for adb utils (use ip:port if only IP is given)
    selector = device if ":" in device else f"{device}:5555"

    # optional: prints for debugging; do NOT change suite
    serial = get_serial_number(selector) or selector
    board, display = get_product_details(selector)
    focused = get_focused_app(selector)
    print(f"Selected device: {serial} | {board} / {display}")
    print(f"Focused app: {focused}")

    target = _pick_target_by_focus(focused)
    print(f"Running test target: {target} (based on focused app)")

    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    html = str(REPORTS / f"report_{Path(target).name}_{ts}.html")

    args = [
        target,
        "-q",
        "--maxfail=1",
        "--disable-warnings",
        "--html", html, "--self-contained-html",
    ]
    return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
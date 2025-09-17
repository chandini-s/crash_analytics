from __future__ import annotations
from pathlib import Path
import os, sys, datetime as dt, subprocess, shlex
import pytest
import re

# --- your existing helpers (adjust names if different) ---
from utils import (
    get_focused_app,  # get_focused_app(device_id) -> str
    get_product_details,  # get_product_details(device_id) -> (board, display_name)
    get_serial_number,  # get_serial_number(device_id) -> str
)

PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"

# --- keep only selected fields in pytest-html "Environment" table -------------
import platform

try:
    from pytest_metadata.plugin import metadata_key

    _NEW_MD = True
except Exception:
    _NEW_MD = False


class _TidyEnvPlugin:
    def __init__(self, serial="", board="", display=""):
        self.serial = serial;
        self.board = board;
        self.display = display

    def pytest_configure(self, config):
        md = config.stash[metadata_key] if _NEW_MD else getattr(config, "_metadata", {})
        try:
            md.clear()
        except Exception:
            for k in list(md.keys()): del md[k]
        md["Python"] = platform.python_version()
        md["Platform"] = platform.platform()
        if self.serial:  md["Serial"] = self.serial
        if self.board:   md["Board details"] = self.board
        if self.display: md["Display name"] = self.display


# -----------------------------------------------------------------------------

# ---------- small shell helpers ----------
def run(cmd: str) -> tuple[int, str, str]:
    p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, out.strip(), err.strip()


def adb_connect(ip_port: str) -> None:
    # ensure port
    if ":" not in ip_port:
        ip_port += ":5555"
    # connect (idempotent)
    run(f"adb disconnect {ip_port}")
    code, out, err = run(f"adb connect {ip_port}")
    if code != 0:
        raise RuntimeError(f"adb connect failed: {err or out}")
    # quick sanity check the device is visible
    code, out, _ = run("adb devices")
    if ip_port.split(":")[0] not in out:
        # sometimes adb shows serial instead of ip; let callers use the serial that utils returns
        pass


def pick_target(focused_app: str, override: str | None) -> str:
    """
    Map focused app (or override) to a pytest target path.
    """
    if override and override.lower() != "auto":
        return {
            "tests_mtr": "testcases/tests_mtr",
            "tests_zoom": "testcases/tests_zoom",
            "tests_device_mode": "testcases/tests_device_mode",
            "tests_oobe": "testcases/tests_oobe",
            "tests_scripts": "tests_scripts",
        }.get(override, "tests_scripts")

    f = (focused_app or "").lower()
    if "teams" in f:              return "testcases/tests_mtr"
    if "zoom" in f:               return "testcases/tests_zoom"
    if "oobe" in f or "settings" in f:
        return "testcases/tests_oobe"
    # default bucket for device-mode style tests
    return "testcases/tests_device_mode"


def get_device_from_env() -> str:
    """
    Jenkins passes DEVICE or DEVICES. We take DEVICE if set, else the first from DEVICES.
    """
    dev = os.getenv("DEVICE", "").strip()
    if dev:
        return dev
    devs = os.getenv("DEVICES", "").strip()
    if devs:
        # split by comma/space/semicolon
        parts = [p.strip() for p in re.split(r"[\s,;]+", devs) if p.strip()]
        if parts:
            return parts[0]
    raise RuntimeError("No device provided. Set Jenkins parameter DEVICE (or DEVICES).")


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def run_selected_pytests(target: str) -> int:
    os.environ.pop("JAVA_HOME", None)
    os.environ.pop("GIT_COMMIT", None)
    os.environ.pop("GIT_URL", None)
    os.environ.pop("GIT_BRANCH", None)
    os.environ.pop("WORKSPACE", None)

    device_ip = os.getenv("DEVICE", "").strip() or os.getenv("DEVICES", "").split(",")[0].strip()
    serial_no = get_serial_number(device_ip)
    board, display_name = get_product_details(device_ip)
    focused_app = get_focused_app(device_ip)

    ensure_reports_dir()
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    html = str(REPORTS_DIR / f"report_{Path(target).name}_{stamp}.html")

    args = [
        target, "-q", "-s", "--maxfail=1", "--disable-warnings",
        "--html", html, "--self-contained-html",
        # we no longer pass many --metadata pairs; the plugin will control the table
    ]

    return pytest.main(args, plugins=[_TidyEnvPlugin(serial_no, board, display_name)])


# ============== the one test Jenkins calls =================
def test_drive_from_jenkins():
    """
    End-to-end driver:
      - read DEVICE/RUN_TARGET from env
      - adb connect
      - get serial, board, focused app
      - pick suite
      - run that suite
    """
    device_ip = os.getenv("DEVICE", "").strip() or os.getenv("DEVICES", "").split(",")[0].strip()
    if not device_ip:
        pytest.fail("DEVICE/DEVICES not provided by Jenkins.")

    # 1) connect
    adb_connect(device_ip)

    # 2) normalize device selector to use with your utils
    #    Many utils accept either IP:port or adb serial. Use whatever your utils expect.
    device_selector = device_ip if ":" in device_ip else f"{device_ip}:5555"

    # 3) metadata & focused app
    serial = get_serial_number(device_selector)
    board, display = get_product_details(device_selector)
    focused = get_focused_app(device_selector)

    print(f"\nSelected device: {serial} | {board} / {display}")
    print(f"Focused app: {focused}")

    # 4) choose suite (honor RUN_TARGET override)
    run_target = (
            os.getenv("RUN_TARGET") or os.getenv("TEST_TARGET")
            or ("mtr" if os.getenv("JENKINS_URL") else "auto")
    ).strip().lower()
    target_path = pick_target(focused, run_target)
    print(f"Running test target: {target_path} (override={run_target})")

    # 5) run the selected tests as a nested pytest session
    rc = run_selected_pytests(target_path)
    assert rc == 0, f"Pytest returned non-zero exit code {rc} for {target_path}"


# Also allow: python tests_run.py
if __name__ == "__main__":
    # run as a plain script
    sys.exit(pytest.main(["-q", __file__, "-s"]))
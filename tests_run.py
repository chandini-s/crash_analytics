from __future__ import annotations

from pathlib import Path
import os, sys, datetime as dt, subprocess, shlex, platform, re
import pytest

# ---- your helpers (keep the same imports you already have) --------------------
from utils import (
    get_focused_app,  # get_focused_app(device_id) -> str
    get_product_details,  # get_product_details(device_id) -> (board, display_name)
    get_serial_number,  # get_serial_number(device_id) -> str | None
)

# ------------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"


# ========== small shell helpers ==========
def run(cmd: str) -> tuple[int, str, str]:
    p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, out.strip(), err.strip()


def adb_connect(ip_port: str) -> None:
    """Idempotent adb connect; adds :5555 when only an IP is provided."""
    if ":" not in ip_port:
        ip_port += ":5555"
    run(f"adb disconnect {ip_port}")
    code, out, err = run(f"adb connect {ip_port}")
    if code != 0:
        raise RuntimeError(f"adb connect failed: {err or out}")
    # sanity: ensure adb sees *something* for this host (adb may list serial instead of IP)
    run("adb devices")


# ========== choose which tests to run ==========
def pick_target(focused_app: str, override: str | None) -> str:
    """
    Map focused app (or an explicit override) to a pytest target path.
    Accepts short forms ('mtr', 'zoom', 'oobe', 'device_mode') and legacy forms ('tests_mtr', ...).
    """
    MAP = {
        # short names
        "mtr": "testcases/tests_mtr",
        "zoom": "testcases/tests_zoom",
        "oobe": "testcases/tests_oobe",
        "device_mode": "testcases/tests_device_mode",
        "device-mode": "testcases/tests_device_mode",

        # legacy names people may pass
        "tests_mtr": "testcases/tests_mtr",
        "tests_zoom": "testcases/tests_zoom",
        "tests_oobe": "testcases/tests_oobe",
        "tests_device_mode": "testcases/tests_device_mode",
        "tests_device-mode": "testcases/tests_device_mode",
    }

    o = (override or "").strip().lower()
    if o and o != "auto":
        return MAP.get(o, "testcases/tests_mtr")

    f = (focused_app or "").lower()
    if "teams" in f:            return MAP["mtr"]
    if "zoom" in f:            return MAP["zoom"]
    if "oobe" in f or "settings" in f:
        return MAP["oobe"]
    # default bucket for device-mode style tests
    return MAP["device_mode"]


def get_device_from_env() -> str:
    """
    Jenkins passes DEVICE or DEVICES. Prefer DEVICE; else first from DEVICES.
    """
    dev = os.getenv("DEVICE", "").strip()
    if dev:
        return dev
    devs = os.getenv("DEVICES", "").strip()
    if devs:
        parts = [p.strip() for p in re.split(r"[\s,;]+", devs) if p.strip()]
        if parts:
            return parts[0]
    raise RuntimeError("No device provided. Set Jenkins parameter DEVICE (or DEVICES).")


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ========== limit pytest-html Environment to ONLY what you asked ==========
try:
    from pytest_metadata.plugin import metadata_key

    _NEW_MD = True
except Exception:
    _NEW_MD = False


class _TidyEnvPlugin:
    def __init__(self, serial="", board="", display=""):
        self.serial = serial
        self.board = board
        self.display = display

    def pytest_configure(self, config):
        md = config.stash[metadata_key] if _NEW_MD else getattr(config, "_metadata", {})
        # wipe default Jenkins/pytest metadata
        try:
            md.clear()
        except Exception:
            for k in list(md.keys()):
                del md[k]
        # add only the requested fields
        md["Python"] = platform.python_version()
        md["Platform"] = platform.platform()
        if self.serial:  md["Serial"] = self.serial
        if self.board:   md["Board details"] = self.board
        if self.display: md["Display name"] = self.display


# ========== run the selected tests as a nested pytest session ==========
def run_selected_pytests(target: str) -> int:
    """
    Launch a fresh pytest session against the selected folder.
    """
    # avoid noisy env keys in report
    for k in ("JAVA_HOME", "GIT_COMMIT", "GIT_URL", "GIT_BRANCH", "WORKSPACE"):
        os.environ.pop(k, None)

    # fetch metadata for the Environment table
    device_ip = os.getenv("DEVICE", "").strip() or os.getenv("DEVICES", "").split(",")[0].strip()
    serial_no = get_serial_number(device_ip) or device_ip
    board, display_name = get_product_details(device_ip)
    focused_app = get_focused_app(device_ip)

    ensure_reports_dir()
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    html = str(REPORTS_DIR / f"report_{Path(target).name}_{ts}.html")

    # guard: if mapping points to a non-existent path, fall back to MTR
    if not Path(target).exists():
        print(f"WARNING: target '{target}' does not exist; falling back to 'testcases/tests_mtr'")
        target = "testcases/tests_mtr"

    args = [
        target,
        "-q",
        "-s",
        "--maxfail=1",
        "--disable-warnings",
        "--html", html,
        "--self-contained-html",
        # do NOT pass --metadata here; _TidyEnvPlugin controls the table
    ]

    return pytest.main(args, plugins=[_TidyEnvPlugin(serial_no, board, display_name)])


# ================= main driver as a single pytest test ==================
def test_drive_from_jenkins():
    """
    End-to-end driver:
      - read DEVICE/RUN_TARGET from env
      - adb connect
      - get serial, board, focused app
      - pick suite
      - run that suite
    """
    device_ip = get_device_from_env()
    adb_connect(device_ip)

    # Use whatever your utils expect for selection; normalize if needed
    device_selector = device_ip if ":" in device_ip else f"{device_ip}:5555"

    serial = get_serial_number(device_selector) or device_selector
    board, display = get_product_details(device_selector)
    focused = get_focused_app(device_selector)

    print(f"\nSelected device: {serial} | {board} / {display}")
    print(f"Focused app: {focused}")

    # Accept either RUN_TARGET or TEST_TARGET; on Jenkins default to mtr to avoid 'auto'
    run_target = (
            os.getenv("RUN_TARGET") or os.getenv("TEST_TARGET")
            or ("mtr" if os.getenv("JENKINS_URL") else "auto")
    ).strip().lower()

    target_path = pick_target(focused, run_target)
    print(f"Running test target: {target_path} (override={run_target})")

    rc = run_selected_pytests(target_path)
    assert rc == 0, f"Pytest returned non-zero exit code {rc} for {target_path}"


if __name__ == "__main__":
    # Allow running as a plain script, useful for local debugging.
    # Example: python tests_run.py mtr
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    # mimic CI behavior
    focused = ""
    run_target = arg or os.getenv("RUN_TARGET") or os.getenv("TEST_TARGET") or "auto"
    print(f"[local] run_target={run_target}")
    # spin up a tiny pytest session that calls the test above
    raise SystemExit(pytest.main(["-q", __file__]))
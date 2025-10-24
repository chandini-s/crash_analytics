"""Run tests per service provider (local providers.json):
APPLY_PROFILE → wait for device online → set timezone → read focus → run tests.
"""

from __future__ import annotations
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
import pytest

from utils import (
    get_focused_app,
    get_serial_number,
    get_product_details,
    get_selected_device,
    adb ,
)

# ───────────────────────── config ─────────────────────────
ROOT = Path(__file__).resolve().parent
PROVIDERS_JSON_PATH = ROOT / "service_provider.json"  # local only

# Fixed inside the profile payload (same for all providers)
PROFILE_COUNTRY = "Germany"
PROFILE_LANGTAG = "en-US"
PROFILE_TIMEZONE_ID = "Europe/Berlin"

# Real DUT timezone (set via ADB after boot)
DUT_TIMEZONE = "Asia/Kolkata"

# Wait tuning
TCP_CONNECT_RETRY_SEC = 3
TCP_CONNECT_TIMEOUT_SEC = 180  # total time to get back online over TCP


def reports_dir() -> Path:
    rd = os.getenv("REPORTS_DIR")
    if rd:
        return Path(rd)
    ws = os.getenv("WORKSPACE")
    if ws:
        return Path(ws) / "reports"
    return ROOT / "reports"


def pick_target_by_focus(focused: str) -> str:
    """Pick pytest target based on focused app name."""
    focused_app = (focused or "").lower()
    if "zoom" in focused_app:
        return "testcases/tests_zoom.py"
    if "teams" in focused_app or "mtr" in focused_app or "microsoft.teams" in focused_app:
        return "testcases/tests_mtr.py"
    if "frogger" in focused_app or "device_mode" in focused_app:
        return "testcases/tests_device_mode.py"
    return "testcases"


# ───────────────────── providers ─────────────
def load_providers_local() -> list[str]:
    """
    providers.json formats accepted:
      ["ZOOM","MTR"]
      {"providers":["ZOOM","MTR"]}
      [{"service":"ZOOM"},{"service":"MTR"}]
    """
    if not PROVIDERS_JSON_PATH.exists():
        raise FileNotFoundError(f"providers.json not found at {PROVIDERS_JSON_PATH}")

    data = json.loads(PROVIDERS_JSON_PATH.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "providers" in data:
        data = data["providers"]

    providers: list[str] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                providers.append(item.strip().upper())
            elif isinstance(item, dict) and "service" in item:
                providers.append(str(item["service"]).strip().upper())
            else:
                raise ValueError("Unsupported providers.json item format")
    else:
        raise ValueError("providers.json must be a list or an object with 'providers'")

    if not providers:
        raise ValueError("providers.json contains no providers")
    return providers


def adb_shell(selector: str, command: str, check: bool = False) -> int:
    return adb(selector, ["shell", command], check=check)


def is_tcp(selector: str) -> bool:
    return ":" in selector and selector.split(":")[0].replace(".", "").isdigit()


def wait_for_device_simple(selector: str) -> None:
    """
    USB: use `adb -s <serial> wait-for-device` (blocks until online).
    TCP: loop `adb connect <ip:port>` then check `adb -s <ip:port> get-state == device`.
    """
    if not is_tcp(selector):
        # USB path: just block until device is seen again
        adb(selector, ["wait-for-device"], check=True)
        return

    # TCP path (reboot breaks the session): keep try connecting + get-state
    deadline = time.time() + TCP_CONNECT_TIMEOUT_SEC
    while time.time() < deadline:
        # try connect
        print(f"[ADB] adb connect {selector}")
        proc = subprocess.run(["adb", "connect", selector],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.stdout:
            print(proc.stdout.strip())

        # check state
        st = subprocess.run(["adb", "-s", selector, "get-state"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out = (st.stdout or "").strip().lower()
        print(f"[ADB] get-state: {out}")
        if "device" in out:
            return

        time.sleep(TCP_CONNECT_RETRY_SEC)

    raise TimeoutError(f"Timed out waiting for TCP device to be online ({TCP_CONNECT_TIMEOUT_SEC}s)")


def apply_service_profile(selector: str, service_provider: str) -> None:
    """
    Broadcast APPLY_PROFILE with fixed regional settings & serviceProviderDpmName.
    """
    profile = {
        "version": 1,
        "regionalSettings": {
            "country": PROFILE_COUNTRY,
            "timeZoneId": PROFILE_TIMEZONE_ID,
            "languageTag": PROFILE_LANGTAG,
        },
        "networkConfiguration": {
            "wired": {"ipAssignmentType": "DHCP", "proxyAssignmentType": "NONE"}
        },
        "serviceProviderDpmName": service_provider,
    }
    json_str = json.dumps(profile, separators=(",", ":"))
    action = "com.logitech.oobe_settings.action.APPLY_PROFILE"
    receiver = "com.logitech.oobe_settings/.ProvisioningProfileReceiver"
    cmd = f"am broadcast -a {action} -n {receiver} --es profile_json '{json_str}'"
    adb_shell(selector, cmd)


def set_dut_timezone(selector: str, tz: str) -> None:
    adb(selector, ["root"])  # ok if it fails
    adb_shell(selector, "settings put global auto_time_zone 0")
    adb_shell(selector, f"setprop persist.sys.timezone {shlex.quote(tz)}")
    adb_shell(selector, "getprop persist.sys.timezone")


# ───────────────────── one provider cycle ─────────────────
def run_one_cycle(selector: str, reports: Path, provider_label: str) -> int:
    """ Run one test cycle for given provider."""
    serial = get_serial_number(selector) or selector
    board, display = get_product_details(selector)
    focused = get_focused_app(selector)

    print(f"Selected device: {serial} | {board} / {display}")
    print(f"Focused app: {focused}")

    target = pick_target_by_focus(focused)
    print(f"Running test target: {target} (based on focused app)")

    reports.mkdir(parents=True, exist_ok=True)
    html = (reports/ f"index_{provider_label}.html").resolve()
    junit_xml = (reports / f"results_{provider_label}.xml").resolve()

    args = [
        target,
        "-q",
        "--disable-warnings",
        "--html", str(html),
        "--self-contained-html",
        f"--junit-xml={junit_xml}",
    ]
    return pytest.main(args)


# ────────────────────────────── main ─────────────────────
def main() -> int:
    # keep env clean for pytest plugins
    for k in ("JAVA_HOME", "WORKSPACE", "GIT_URL"):
        os.environ.pop(k, None)

    device = "10.91.208.243"
    selector = device if ":" in device else f"{device}:5555"

    providers = load_providers_local()
    reports = reports_dir()
    final_rc = 0

    for sp in providers:
        label = sp.upper()
        print("\n" + "=" * 80)
        print(f"[{label}] APPLY_PROFILE → wait-for-device (online) → set ADB timezone → read focus → run tests")
        print("=" * 80)

        try:
            apply_service_profile(selector, label)
            time.sleep(60)
        except Exception as e:
            print(f"[WARN] Failed to apply service profile for {label}: {e}")

        # Wait until device shows up again, then set time
        try:
            wait_for_device_simple(selector)
        except Exception as e:
            print(f"[WARN] Device did not come online for {label}: {e}")

        try:
            set_dut_timezone(selector, DUT_TIMEZONE)
        except Exception as e:
            print(f"[WARN] Failed to set DUT timezone for {label}: {e}")

        rc = run_one_cycle(selector, reports, label)
        if final_rc == 0 and rc != 0:
            final_rc = rc

    return final_rc


if __name__ == "__main__":
    raise SystemExit(main())

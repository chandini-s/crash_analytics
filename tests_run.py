# tests_run.py
from pathlib import Path
import os, json, re, subprocess
import pytest
from utils import (
    get_connected_devices, get_selected_device, get_serial_number,
    get_product_details, get_focused_app
)

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"  # kept for auth/cookie if you still use them


# ---------- device list from Jenkins env ----------
def _devices_from_env() -> list[str]:
    """
    DEVICES_JSON='[{"setup":"10.91.231.25:5555"},{"setup":"10.91.231.82"}]'
    or
    DEVICES='10.91.231.25 10.91.231.82;10.91.231.51'
    Returns ['ip:port', ...]
    """
    s = (os.getenv("DEVICES_JSON") or "").strip()
    if s:
        data = json.loads(s)
        out = []
        for x in data:
            ip = x["setup"] if isinstance(x, dict) else str(x)
            out.append(ip if ":" in ip else f"{ip}:5555")
        return out

    s2 = (os.getenv("DEVICES") or "").strip()
    if s2:
        ips = [p for p in re.split(r"[\s,;]+", s2) if p]
        return [ip if ":" in ip else f"{ip}:5555" for ip in ips]

    return []  # no env provided -> use your existing interactive flow


def _adb_connect(ip_port: str) -> None:
    # be idempotent and quiet
    subprocess.run(["adb", "disconnect", ip_port], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = subprocess.run(["adb", "connect", ip_port], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"adb connect failed for {ip_port}: {r.stderr.strip()}")


def _pick_suite(focused_app: str) -> str:
    fa = focused_app.lower()
    if "teams" in fa:
        return "testcases/tests_mtr"
    if "zoom" in fa:
        return "testcases/tests_zoom"
    if "device_mode" in fa:
        return "testcases/tests_device_mode"
    if "oobe_settings" in fa or "oobe" in fa:
        return "testcases/tests_oobe"
    # default: run everything
    return "testcases"


def run_once_for_device(selected_device: str) -> int:
    """Run your existing flow for one selected device and return pytest exit code."""
    serial_no = get_serial_number(selected_device)
    board, display_name = get_product_details(selected_device)
    focused_app = get_focused_app(selected_device)
    print(f"Detected focused app: {focused_app}")

    test_target = _pick_suite(focused_app)

    # ensure reports dir
    os.makedirs("reports/report_testcases", exist_ok=True)
    report_html = f"reports/report_testcases/run_{serial_no}.html"

    # run pytest on that suite
    return pytest.main([
        test_target,
        "-q",
        f"--html={report_html}",
        "--self-contained-html",
    ])


def main():
    # Make sure Java UI tools don't steal focus in some labs
    os.environ.pop("JAVA_HOME", None)

    ip_list = _devices_from_env()

    exit_codes = []

    if ip_list:
        # Jenkins (or local env) provided explicit devices: connect and run each
        for ip in ip_list:
            print(f"\n=== Connecting to {ip} ===")
            _adb_connect(ip)
            # After connect, pick the matching device from adb devices
            devices = get_connected_devices()
            # Match by the ip:port string
            selected = next((d for d in devices if ip in d), None)
            if not selected:
                raise RuntimeError(f"Connected to {ip}, but device not visible in 'adb devices'. Seen: {devices}")
            os.environ["ANDROID_SERIAL"] = selected  # route all adb calls to this device
            code = run_once_for_device(selected)
            exit_codes.append((ip, code))
            # optional clean up between devices
            subprocess.run(["adb", "disconnect", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # No DEVICES provided: fall back to your current selection flow
        adb_devices = get_connected_devices()
        selected_device = get_selected_device()  # your existing chooser
        os.environ["ANDROID_SERIAL"] = selected_device
        code = run_once_for_device(selected_device)
        exit_codes.append(("selected", code))

    # fail pipeline if any device failed
    if any(code != 0 for _, code in exit_codes):
        for ip, code in exit_codes:
            print(f"[SUMMARY] {ip}: pytest exit code {code}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

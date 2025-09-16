# tests_run.py
import os, re, subprocess
from pathlib import Path
from utils import (
    get_connected_devices, get_selected_device, connect,  # adb helpers you already have
    get_focused_app, get_product_details, get_serial_number,
)

ROOT = Path(__file__).resolve().parent


def _devices_from_env() -> list[str]:
    s = os.environ.get("DEVICES", "").strip()
    if not s:
        return []
    ips = [p.strip() for p in re.split(r"[\s,;]+", s) if p.strip()]
    return [ip if ":" in ip else f"{ip}:5555" for ip in ips]


def _resolve_suite(focused_app: str, choice: str) -> str:
    if choice and choice != "auto":
        return f"testcases/{choice}"
    fa = (focused_app or "").lower()
    if "teams" in fa: return "testcases/tests_mtr"
    if "zoom" in fa: return "testcases/tests_zoom"
    if "oobe" in fa: return "testcases/tests_oobe"
    if "device" in fa or "settings" in fa: return "testcases/tests_device_mode"
    return "tests_scripts"


def _run_pytest(target: str, label: str):
    report = ROOT / f"reports/report_{label}.html"
    cmd = f'pytest -q {target} --html="{report}" --self-contained-html'
    subprocess.run(cmd, check=True, shell=True)


def main():
    os.environ.pop("JAVA_HOME", None)

    device_list = _devices_from_env()
    if not device_list:
        # fallback to your current interactive/local logic
        device_list = [get_selected_device()]

    for dev in device_list:
        # if IP -> connect, else assume already selected serial
        if re.match(r'\\d+\\.\\d+\\.\\d+\\.\\d+(?::\\d+)?$', dev):
            connect(dev)  # should adb connect and return/select serial
        serial = get_selected_device()
        focused = get_focused_app(serial)
        suite = _resolve_suite(focused, os.environ.get("TEST_TARGET", "auto"))
        label = serial.replace(':', '_').replace('.', '-')
        print(f"[INFO] Running suite={suite} on device={serial} (focused={focused})")
        _run_pytest(suite, label)


if __name__ == "__main__":
    main()

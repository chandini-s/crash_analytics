import json
from pathlib import Path
import subprocess
import re
import os
from typing import Optional


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
METADATA_PATH = ROOT /"metadata.json"

_SELECTED_SERIAL: Optional[str] = None

def _run(cmd, check=True):
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def _pick_serial_from_devices_listing(match: str) -> Optional[str]:
    out = _run(["adb", "devices", "-l"], check=False).stdout.splitlines()
    for line in out:
        if not line.strip() or line.startswith("List of"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            if match in line or match == serial:
                return serial
    return None

def get_selected_device() -> str:
    """
    Resolve and cache the selected device serial.

    Jenkins can pass:
      DEVICE  = '10.91.231.25' or '10.91.231.25:5555' or a USB serial
      DEVICES = 'ip1, ip2, ...' (first non-empty is used)
    Fallback: first non-empty line from <WORKSPACE>/config/devices.txt
    """
    global _SELECTED_SERIAL
    if _SELECTED_SERIAL:
        return _SELECTED_SERIAL

    # 1) Jenkins env: DEVICE first, then DEVICES list
    def _clean(s: str) -> str:
        return s.strip().strip('"').strip("'")

    dev = _clean(os.getenv("DEVICE", ""))
    if not dev:
        raw = os.getenv("DEVICES", "")
        if raw:
            for tok in re.split(r"[,\s]+", raw):
                tok = _clean(tok)
                if tok:
                    dev = tok
                    break

    # 2) Fallback: Jenkins workspace file written by pipeline
    if not dev:
        ws = os.getenv("WORKSPACE", ".")
        f = Path(ws) / "config" / "devices.txt"
        if f.exists():
            for line in f.read_text().splitlines():
                line = _clean(line)
                if line:
                    dev = line
                    break

    if not dev:
        raise RuntimeError(
            "DEVICE not provided. Set DEVICE in Jenkins (or put one line in config/devices.txt)."
        )

    # 3) If it's an IP, normalize to :5555 and connect; else treat as serial
    ip_re = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$")
    if ip_re.match(dev):
        ip = dev if ":" in dev else f"{dev}:5555"
        _run(["adb", "disconnect", ip], check=False)  # avoid stale sessions
        _run(["adb", "connect", ip], check=False)
        serial = _pick_serial_from_devices_listing(ip)
        if not serial:
            raise RuntimeError(f"Connected to {ip}, but could not resolve serial from `adb devices -l`.")
    else:
        serial = dev  # already a USB serial

    _SELECTED_SERIAL = serial
    return serial

def adb(serial: str, args=None, check=True, timeout=None):
    """Wrapper that always scopes to the selected device."""
    if args is None:
        args = []
    if isinstance(args, str):
        #split on spaces
        args = args.split()
    cmd = ["adb", "-s", str(serial)] + list(args)
    return subprocess.run(cmd, text=True, capture_output=True, check=check, timeout=timeout)


def get_serial_number(device_selected: str ) -> str | None:
    """Return the Android ro.serialno of the selected device."""
    try:
        out = adb(device_selected, ["shell", "getprop", "ro.serialno"]).stdout.strip()
        match = re.search(r'\[ro\.serialno\]: \[(.*?)\]', out)
        if match:
            serial_number = match.group(1)
            print("Serial number:", serial_number)
            return serial_number
        return out or None
    except subprocess.CalledProcessError:
        return None

# (optional) helpers you already have can call adb():

def _read_text(p: Path) -> str:
    try:
        return Path(p).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def get_auth_and_cookie():
    # Jenkins can pass these as String Parameters
    auth = os.getenv("AUTH", "").strip()
    cookie = os.getenv("COOKIE", "").strip()
    if auth or cookie:
        return auth, cookie
    # fallback to files so local dev still works


def have_auth() -> bool:
    auth, cookie = get_auth_and_cookie()
    return bool(auth or cookie)


def build_headers() -> dict:
    auth, cookie = get_auth_and_cookie()
    headers = {"accept": "application/json"}
    if auth:
        headers["Authorization"] = auth
    if cookie:
        headers["Cookie"] = cookie
    return headers
# ---------- helpers ----------
def read_text(p: Path) -> str | None:
    """
      Reads a text file and returns its content as a stripped string.
      Parameters:
      -----------
      p : Path to the file.
      Returns:
      --------
      str | None
          File content or None if file is missing or empty.
      """
    try:
        file_content = p.read_text(encoding="utf-8").strip()
        return file_content if file_content else None
    except FileNotFoundError:
        return None


def build_headers() -> dict:
    """
    Builds HTTP headers for API requests using JWT and Cookie from config files.
    Returns:
    --------
    dict
        Dictionary of headers including Authorization and Cookie.
    Raises:
    -------
    RuntimeError
        If neither JWT nor Cookie is configured.
    """
    headers = {"Accept": "application/json"}
    jwt,cookie = get_auth_and_cookie()
    if jwt:
        headers["Authorization"] = jwt if jwt.lower().startswith("bearer ") else f"Bearer {jwt}"
    if cookie:
        headers["Cookie"] = cookie
    if "Authorization" not in headers and "Cookie" not in headers:
        raise RuntimeError("No auth configured. Put JWT in config/auth.txt and/or Cookie in config/cookie.txt")
    return headers

def get_focused_app(adb_device):
    """Fetches the currently focused app on the device using adb shell dumpsys."""
    try:
        # Run the command and capture output
        active_app = f'adb -s {adb_device} shell "dumpsys window | grep mFocusedApp"'
        result = subprocess.check_output(
            active_app,
            stderr=subprocess.STDOUT,
            shell=True,
            text=True
        )

        # Split lines and find last non-null mFocusedApp line
        lines = [line.strip() for line in result.strip().split('\n') if 'mFocusedApp=' in line]
        for line in reversed(lines):
            if 'null' not in line:
                # Extract package/activity from the line
                parts = line.split()
                for part in parts:
                    if '/' in part:
                        return part.strip()  # This is the package/activity
        return None
    except subprocess.CalledProcessError as e:
        print("Error:", e.output)
        return None

def get_product_details(adb_device):
    """Fetches product details using adb shell getprop."""
    command = f'adb -s {adb_device} shell "getprop | grep ro.product"'
    output = subprocess.check_output(command, shell=True, text=True)

    # Use regex to find the serial number
    match_board = re.search(r'\[ro\.product\.board]: \[(.*?)\]', output)
    match_display_name = re.search(r'\[ro\.product\.displayname]: \[(.*?)\]', output)
    if match_board and match_display_name:
        board = match_board.group(1)
        display_name = match_display_name.group(1)
        print(f"Name Details: {display_name}")
        print(f"Board Details: {board}")
        return board, display_name

def adb(serial: str, args: list[str], check=True, timeout=None):
    """
     Runs an ADB command for the specified device.
     Parameters:
     serial : str
         ADB device serial.
     args : list[str]
         List of ADB command arguments.
     check : bool
         Whether to raise an error on failure.
     timeout : Optional[int]
         Timeout in seconds.
     Returns:
     subprocess.CompletedProcess
         Result of the subprocess execution.
     """
    return subprocess.run(["adb", "-s", serial] + args, check=check, capture_output=True, text=True, timeout=timeout)


def read_json(path):
    """ This function loads a JSON file from the specified path and parses it into a Python object
    (e.g., a dictionary or list) using the `json` module."""
    with open(path, mode='r') as file:
        return json.load(file)
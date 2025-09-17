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
    Jenkins can pass either:
      - DEVICE   = '10.91.231.25' or '10.91.231.25:5555' or a serial
      - DEVICES  = 'ip1,ip2,...'  (first is used)
    Fallback: exactly one attached device.
    """
    global _SELECTED_SERIAL
    if _SELECTED_SERIAL:
        return _SELECTED_SERIAL

    # 1) Jenkins env
    dev = (os.getenv("DEVICE") or "").strip()
    if not dev:
        # allow a list: take the first non-empty entry
        devs = [p.strip() for p in re.split(r"[,;\s]+", os.getenv("DEVICES", "")) if p.strip()]
        if devs:
            dev = devs[0]

    if dev:
        # If IP given, ensure :5555 and adb connect
        if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$", dev):
            ip = dev if ":" in dev else f"{dev}:5555"
            _run(["adb", "disconnect", ip], check=False)  # avoid stale state
            _run(["adb", "connect", ip], check=False)
            serial = _pick_serial_from_devices_listing(ip)
            if not serial:
                raise RuntimeError(f"Connected to {ip}, but couldn't resolve its serial from 'adb devices -l'.")
        else:
            # looks like a serial already
            serial = dev
        _SELECTED_SERIAL = serial
        os.environ["ADB_SERIAL"] = serial  # convenience for tools that honor it
        return serial

    # 2) Fallback: exactly one attached device
    out = _run(["adb", "devices"], check=False).stdout.splitlines()
    serials = [l.split()[0] for l in out if l.strip().endswith("device") and not l.startswith("List of")]
    if len(serials) != 1:
        raise RuntimeError("Zero or multiple devices attached. Set DEVICE/DEVICES in Jenkins.")
    _SELECTED_SERIAL = serials[0]
    os.environ["ADB_SERIAL"] = _SELECTED_SERIAL
    return _SELECTED_SERIAL


def adb(serial: str, args=None, check=True, timeout=None):
    """Wrapper that always scopes to the selected device."""
    if args is None:
        args = []
    if isinstance(args, str):
        #split on spaces
        args = args.split()
    cmd = ["adb", "-s", str(serial)] + list(args)
    return subprocess.run(cmd, text=True, capture_output=True, check=check, timeout=timeout)

# def get_serial_number(_: str | None = None) -> str:
#     """Return the Android ro.serialno of the selected device."""
#     out = adb("shell", "getprop ro.serialno").stdout.strip()
#     if not out:
#         raise RuntimeError("ro.serialno is empty")
#     return out


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
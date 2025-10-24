"""Utility functions for device management and API interaction."""

from pathlib import Path
import subprocess
import shlex
import re
import os
from typing import Optional
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
METADATA_PATH = ROOT /"metadata.json"

_SELECTED_SERIAL: Optional[str] = None    # cache for selected device serial


def _run(cmd, check=True):
    """ Helper to run a command and capture output."""
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
    Resolve and cache the selected device serial number or IP:port.

    Priority order:
      1. Jenkins environment variable 'DEVICE' (preferred), or first entry in 'DEVICES' (comma/space-separated).
      2. Fallback: Read from 'config/devices.txt' in the Jenkins workspace.
      3. If the value is an IP, normalize to IP:5555 and connect via ADB; otherwise, treat as a USB serial.
    Returns:
        str: The resolved device serial or IP:port.
    Raises:
        RuntimeError: If no device is found via environment or config file.
    """
    global _SELECTED_SERIAL
    if _SELECTED_SERIAL:
        return _SELECTED_SERIAL
    # 1) Jenkins env: DEVICE first, then DEVICES list
    def clean(s: str) -> str:
        return s.strip().strip('"').strip("'")
    device = clean(os.getenv("DEVICE", ""))
    if not device:
        raw = os.getenv("DEVICES", "")
        if raw:
            for tok in re.split(r"[,\s]+", raw):
                tok = clean(tok)
                if tok:
                    device = tok
                    break
    # 2) Fallback: Jenkins workspace file written by pipeline
    if not device:
        ws = os.getenv("WORKSPACE", ".")
        f = Path(ws) / "config" / "devices.txt"
        if f.exists():
            for line in f.read_text().splitlines():
                line = clean(line)
                if line:
                    dev = line
                    break
    if not device:
        raise RuntimeError(
            "DEVICE not provided. Set DEVICE in Jenkins (or put one line in config/devices.txt)."
        )
    # 3) If it's an IP, normalize to :5555 and connect; else treat as serial
    ip_re = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$")
    if ip_re.match(device):
        ip = device if ":" in device else f"{device}:5555"
        _run(["adb", "disconnect", ip], check=False)  # avoid stale sessions
        _run(["adb", "connect", ip], check=False)
        serial = _pick_serial_from_devices_listing(ip)
        if not serial:
            raise RuntimeError(f"Connected to {ip}, but could not resolve serial from `adb devices -l`.")
    else:
        serial = device  # already a USB serial

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


def get_auth_and_cookie():
    """ Returns (auth, cookie) from jenkins environment."""
    auth = os.getenv("AUTH", "").strip()
    cookie = os.getenv("COOKIE", "").strip()
    # auth ="eyJraWQiOiJoUm8rK0ZKN1FSdFdcL3FcLzdjQzVwbjNidG5GOFoyQXlcLzMyS3gwS2RwQnFnPSIsImFsZyI6IlJTMjU2In0.eyJhdF9oYXNoIjoiWjhoWkdEUUVSZi11cjNsVmx6Z3BGZyIsInN1YiI6ImE1YjMyOGRhLTI3NmYtNGY3ZC1iYjhjLWFjZWUxMGQyMjdmNSIsImNvZ25pdG86Z3JvdXBzIjpbInMzYnJvd3NlciIsInVzLXdlc3QtMl9WU3NOekh1U2RfTG9naXRlY2hPa3RhIiwic3dfcmVsZWFzZV92aWV3ZXIiLCJob3N0bG9ncyIsIm90YV9tYW5pZmVzdHMiLCJldmVudGxvZ3MiLCJkaWFnbm9zdGljcyIsImJ1Z3JlcG9ydHMiXSwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJjb2duaXRvOnByZWZlcnJlZF9yb2xlIjoiYXJuOmF3czppYW06OjUxMjM3NzcwMDIzNzpyb2xlXC9UZW5qaW5Qcm9kLVdlYnNpdGVpZGVudGl0eXJvbGVzMzRGRTk3NEJCLTRZRFVPUTEwWk9TUyIsImlzcyI6Imh0dHBzOlwvXC9jb2duaXRvLWlkcC51cy13ZXN0LTIuYW1hem9uYXdzLmNvbVwvdXMtd2VzdC0yX1ZTc056SHVTZCIsImNvZ25pdG86dXNlcm5hbWUiOiJMb2dpdGVjaE9rdGFfZ3ZlbmthdGVzaEBsb2dpdGVjaC5jb20iLCJnaXZlbl9uYW1lIjoiR2F1dGFtIiwibm9uY2UiOiJxMzdlZ3pvYXk2VUtGTTFEaG92Y0pzVnVBVEpNTHlMeWd2aWpxU2Q3RldaMHdmSVlheTYxa055YkhDLVh5SlFwVlBsRVBVM2N0TkxtUkRRWmdqX1N5SHNfRzJPeDFlSHZ0QXI3OVJqTWR2dDZMZWZqRkt6TWdWenRfREhEcThfUmh5a18wZEpJQXZnbUpSU3FwR0ZTX0NiWnVhb3BKSUFhcU9iX1U1VXoyNVEiLCJvcmlnaW5fanRpIjoiZGY3MTJmNGEtZWUxNS00OThjLTliMWItNmVkZWVmNjFlOTJjIiwiY29nbml0bzpyb2xlcyI6WyJhcm46YXdzOmlhbTo6NTEyMzc3NzAwMjM3OnJvbGVcL1RlbmppblByb2QtV2Vic2l0ZWlkZW50aXR5cm9sZXMzNEZFOTc0QkItNFlEVU9RMTBaT1NTIl0sImF1ZCI6IjJkcmhlbTdhN2VqOWlyZWMxbTU5cDlyZmdmIiwiaWRlbnRpdGllcyI6W3sidXNlcklkIjoiZ3ZlbmthdGVzaEBsb2dpdGVjaC5jb20iLCJwcm92aWRlck5hbWUiOiJMb2dpdGVjaE9rdGEiLCJwcm92aWRlclR5cGUiOiJTQU1MIiwiaXNzdWVyIjoiaHR0cDpcL1wvd3d3Lm9rdGEuY29tXC9leGsyZmt0b2JlNHBjczFxejR4NyIsInByaW1hcnkiOiJ0cnVlIiwiZGF0ZUNyZWF0ZWQiOiIxNzE2OTg3NjIzMjg5In1dLCJ0b2tlbl91c2UiOiJpZCIsImF1dGhfdGltZSI6MTc2MTI3NzA0NCwibmFtZSI6IkdhdXRhbSIsImV4cCI6MTc2MTMwOTQ0NCwiaWF0IjoxNzYxMjc3MDQ0LCJmYW1pbHlfbmFtZSI6IlZlbmthdGVzaCIsImp0aSI6IjNlZGJmZGIxLWM2YTEtNGY3OS05NTIyLTllNDUyOTY4ZTYzZSIsImVtYWlsIjoiZ3ZlbmthdGVzaEBsb2dpdGVjaC5jb20ifQ.A9a5isbi7ILTckkcbKNtWg4cGyu6SBqhRw-0cKYbq1bBbS2LeY6OqzW6rSye9P32ibo3xpYm76mZvDle9K0JA-ICYhfUD7ZScdDsFFr-6FQy4U02EB4VTNWwy-FUvvy3E8iKi6YR1ZhtcmUEuddV_sl8Hp6BYgNsOIfKsREK_1gbIRBb72xiENqXisoNnksb78zQsr_nee5FOtnOPyw9f1zgr9ZmS-Uu3PXUTProkXkbUdGKnJp1Dkc3pnspOuSs6bu9mPHcT8hgNdJrm6nZs3ddLm5vq62c9zVxeVIxtDjf7PR54s5bArKYpGqnzbZa8oNIAT6w7WtNtS7kOTGSog"
    # cookie = "_ga=GA1.1.2046316337.1756201732; _ga_JCM4J59MSX=GS2.1.s1756356944$o2$g1$t1756357064$j60$l0$h0"
    if auth or cookie:
        return auth, cookie
    # else :
    #     auth = _read_text(CONFIG_DIR / "auth.txt")
    #     cookie = _read_text(CONFIG_DIR / "cookie.txt")
    #     return auth, cookie
    else :
        return False


def have_auth() -> bool:
    """Returns True if either JWT or Cookie is configured."""
    auth, cookie = get_auth_and_cookie()
    return bool(auth or cookie)


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
    Builds HTTP headers for API requests using JWT and Cookie from jenkins environment.
    Returns:
    dict
        Dictionary of headers including Authorization and Cookie.
    Raises:
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


log_file_path = "window_dump.xml"
def run_adb_commands():
    try:
        subprocess.run(["adb", "shell", "uiautomator", "dump"], check=True)
        subprocess.run(["adb", "pull", "/sdcard/window_dump.xml"], check=True)
        print("[INFO] UI dump pulled successfully.")
    except Exception as e:
        print(f"[ERROR] ADB command failed: {e}")

def read_cmd_output_safe():
    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            return f.read().lower()
    except Exception as e:
        print(f"[ERROR] Reading log failed: {e}")
        return ""

def extract_device_code_from_xml():
    try:
        tree = ET.parse(log_file_path)
        root = tree.getroot()
        for node in root.iter("node"):
            text = node.attrib.get("text", "")
            if re.fullmatch(r"[A-Z0-9]{8,}", text):
                return text
    except Exception as e:
        print(f"[ERROR] Could not extract device code: {e}")
    return None

def main():
    run_adb_commands()
    code = extract_device_code_from_xml()
    if code:
        print(f"✅ Device login code found: {code}")
    else:
        print("❌ No valid device login code found.")

if __name__ == "__main__":
    main()
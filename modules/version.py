"""
Fetch device information and CollabOS version via ADB and the Analytics API.

This module provides utilities to:
- Read HTTP headers (JWT or Cookie) via `utils.build_headers`.
- Query the Logitech Analytics API for a single device:
    `GET https://logi-analytics.vc.logitech.com/api/device/{DEVICE_ID}`
- Extract the CollabOS version from the response, trying common key names first
  and falling back to a recursive search through the entire object.
- Optionally retrieve the CollabOS version directly from an attached Android
  device via ADB (`getprop | grep collab`).

Requirements
------------
- `requests` for HTTP calls.
- `adb` available on PATH if using ADB helper (`get_collab_version_from_adb`).
- A JWT or Cookie for the Analytics API (retrieved in `utils.build_headers`).

Usage
-----
    from device_info import get_collabos_version
    version = get_collabos_version("2411FD1LG0A2")
    if version:
        print("CollabOS version:", version)
    else:
        print("Version not found")
Steps
-----
1. Build authenticated headers (via `utils.build_headers`) using either a JWT
   or Cookie (sourced from your local config implementation).
2. Call `get_device_info(device_id)` to fetch the device JSON from the analytics API.
3. Call `get_collabos_version(device_id)` to pull a CollabOS version from either:
   - known keys on the top-level object, or
   - a recursive search (`find_collabos_value`) over nested structures.
4. (Optional) Use `get_collab_version_from_adb` to query an attached device via ADB.

Security & Notes
----------------
- Ensure the JWT/Cookie you pass to the service is scoped properly and kept secure.
- `get_collab_version_from_adb` executes a shell command using `adb`. Avoid passing
  untrusted values for the device serial. Consider using the list-argument form
  of `subprocess` to reduce shell interpretation risk.

"""

from __future__ import annotations
import re
import requests
from typing import Any, Optional, Dict
import subprocess
from utils import build_headers, get_serial_number, get_selected_device


DEVICE =get_selected_device()
API_BASE = "https://logi-analytics.vc.logitech.com/api"
DEVICE_ID = get_serial_number(DEVICE)
REQUEST_TIMEOUT = 30.0


def get_collab_version_from_adb(adb_device):
    """
       Fetch the CollabOS version from a connected Android device using ADB.
       This function issues:
           adb -s <serial> shell "getprop | grep collab"
       and then searches the output for a semantic version pattern like `X.Y.Z`.
       Parameters:
       adb_device : str
           The ADB device serial (as shown by `adb devices`).
       Returns
       Optional[str]
           The CollabOS version in the form `MAJOR.MINOR.PATCH` if found,
           otherwise `None`.
       Raises
            subprocess.CalledProcessError
            If the ADB command fails (non-zero exit).
       FileNotFoundError
           If `adb` is not installed or not found on PATH.
        Notes
       - This uses `shell=True` with a formatted string; avoid passing untrusted
         values to `adb_device`. Prefer using list arguments to `subprocess` for
         stricter safety if you control both ends."""

    cmd = f'adb -s {adb_device} shell "getprop | grep collab"'
    output = subprocess.check_output(cmd, shell=True, text=True)

    match = re.search(r'\[(\d+\.\d+\.\d+)\]', output)
    return match.group(1) if match else None


def find_collabos_value(obj: Any) -> Optional[str]:
    """
    Recursively search `obj` (dict/list) for a key whose name looks like
    CollabOS version (e.g. 'collabOSVersion', 'collabos_version', 'collabVersion', ...)
    Return the first non-empty string value found, or None.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            lower_key = key.lower()
            # basic heuristics: look for 'collab' and 'version' or 'collabos'
            if ("collab" in lower_key and "version" in lower_key) or "collabos" in lower_key or lower_key in (
            "collab", "collabos", "collab_version"):
                if isinstance(value, str) and value.strip():
                    return value.strip()
                # if it's numeric/other, coerce to str
                if value is not None:
                    return str(value)
        # not in immediate keys — recurse into values
        for nested_value in obj.values():
            found = find_collabos_value(nested_value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_collabos_value(item)
            if found:
                return found
    return None


def get_device_info(device_id: str, headers: Optional[Dict[str, str]] = None, timeout: int = 15) -> Dict[str, Any]:
    """
      Fetch the device JSON object from the Analytics API.
      Endpoint:
          GET {API_BASE}/device/{device_id}
      Parameters
      device_id : str
          The device identifier (e.g., serial or unique ID).
      headers : Optional[Dict[str, str]], optional
          HTTP headers for authentication/authorization. If not provided,
          `utils.build_headers()` is called to construct them.
      timeout : int, optional
          Request timeout in seconds (default: 15).
      Returns
      Dict[str, Any]
          Parsed JSON object describing the device.
      Raises
      requests.HTTPError
          If the server returns a non-2xx code (e.g., 401/403/404).
      RuntimeError
          If the response body is not a JSON object (dict).
      """
    if headers is None:
        headers = build_headers()
    url = f"{API_BASE.rstrip('/')}/device/{device_id}"
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected device info response: {type(data)} -> {data}")
    return data


def get_collabos_version(device_id: str = DEVICE_ID, headers: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Return CollabOS version string for `device_id`, or None if not present.
    Raises requests.HTTPError for HTTP/auth errors.
    """
    info = get_device_info(device_id, headers=headers)
    for key in ("collabOSVersion", "collabOsVersion", "collabosVersion", "collab_version", "collabos_version"):
        if key in info and info[key]:
            return str(info[key])
    return find_collabos_value(info)


if __name__ == "__main__":
    """Example usage: fetch and print CollabOS version for the selected device."""
    try:
        version = get_collabos_version()
        if version:
            print("CollabOS version:", version)
        else:
            print("CollabOS version not found in device info JSON.")
    except requests.HTTPError as e:
        # helpful message on auth/403/401/400
        status = getattr(e.response, "status_code", None)
        print(f"HTTP error fetching device info: {status} {e}")
    except Exception as e:
        print("Error:", e)

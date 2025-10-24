"""
Automates the process of rebooting a Logitech device via ADB and polling the Event Logs API
to detect the presence of a `Bort_DiskStats` event within a fixed time window around the reboot.
Flow:
-----
1. Select the first online ADB device.
2. Reboot the device and wait for it to complete booting.
3. Define a fixed time window around the reboot time (-2 min to +5 min).
4.Calls GET /api/eventlogs/{DEVICE_ID}?from=..&to=.. to list items.
5. Poll the Event Logs API every 3 minutes for up to 30 minutes.
6. Look for a `Bort_DiskStats` event and report if found.

Requirements
------------
- Place two files beside this script:
    - auth.txt   -> a single line containing the raw JWT copied from DevTools
                    (use the exact string shown in the request header named
                    `authorization` – do NOT add the word "Bearer")
    - cookie.txt -> a single line containing the full Cookie header value

Usage
-----
    install requirements: pip install -r requirements.txt
    python -u generate_download.py
"""

import time, subprocess, requests, json, fnmatch
from pathlib import PurePath
from datetime import datetime, timedelta, timezone
from utils import get_serial_number, get_selected_device, adb

# ---------- Config ----------
DEVICE = get_selected_device()
API_BASE = "https://logi-analytics.vc.logitech.com/api"
DEVICE_ID = get_serial_number(DEVICE)  # analytics device id
PRE_REBOOT_MIN = 2
POST_REBOOT_MIN = 5
POLL_INTERVAL_MIN = 3
POLL_TIMEOUT_MIN = 30
PAGE_LIMIT = 200
IST = timezone(timedelta(hours=5, minutes=30))


def iso_ist(dt: datetime) -> str:
    """
    Converts a datetime object to ISO8601 format in IST timezone.
    Parameters:
    -----------
    dt : datetime object.
    Returns:
    --------
    str
        ISO8601 string in IST with milliseconds.
    """
    return dt.astimezone(IST).isoformat(timespec="milliseconds")


def get_device_type(headers: dict[str, str], serial: str) -> str:
    """
    Return deviceType for the given device serial using Analytics device endpoint.
    """
    url = f"{API_BASE}/device/{serial}"
    r = requests.get(url, headers=headers, timeout=30)
    try:
        r.raise_for_status()
    except requests.HTTPError:
        msg = f"Failed to get device info for {serial}: {r.status_code} {r.reason}"
        raise RuntimeError(f"get_device_type: {msg}\nResponse content: {r.text}")

    data = r.json() if r.content else {}
    # deviceType usually lives at top level; fallbacks included just in case
    device_type=(
        data.get("type")
        or (data.get("metadata") or {}).get("deviceType")
        or (data.get("device", {}) or {}).get("type")
    )
    if not device_type or not isinstance(device_type, str):
        raise RuntimeError(f"get_device_type: deviceType not found in response: {data}")
    device_type = device_type.strip()
    return device_type


def reboot_and_wait(serial: str) -> datetime:
    """
      Reboots the device via ADB and waits for it to complete booting.
      Parameters:
      serial : str
          ADB device serial.
      Returns:
      datetime
          Reboot trigger time in IST.
      Raises:
      RuntimeError
          If boot completion is not detected within timeout."""
    print("Rebooting device via ADB…")
    trigger_time = datetime.now(IST)
    adb(serial, ["reboot"], check=False)
    print("Waiting for device (adb wait-for-device)…")
    subprocess.run(["adb", "-s", serial, "wait-for-device"], check=True, text=True, timeout=360)
    print("ADB device is online.")
    print("Waiting for sys.boot_completed=1")
    deadline = time.time() + 360
    while time.time() < deadline:
        out = adb(serial, ["shell", "getprop", "sys.boot_completed"], check=False)
        if (out.stdout or "").strip() == "1":
            print("Boot completed.")
            return trigger_time
        time.sleep(2)
    raise RuntimeError("Timed out waiting for boot completion")


def fetch_page(headers: dict, from_iso: str, to_iso: str, offset: int) -> list:
    """
     Fetches a single page of event logs from the API.
     Parameters:
     headers : dict
         HTTP headers.
     from_iso : str
         Start time in ISO format.
     to_iso : str
         End time in ISO format.
     offset : int
         Pagination offset.
     Returns:
         List of event log entries.
     Raises:
     RuntimeError
         If response is not a list.
     """
    url = f"{API_BASE}/eventlogs/{DEVICE_ID}"
    device_type = get_device_type(headers, DEVICE_ID)
    params = {
        "deviceType":device_type,
        "from": from_iso,
        "to": to_iso,
        "limit": PAGE_LIMIT,
        "offset": offset,
    }
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response: {type(data)} -> {data}")
    return data


def scan_window(headers: dict, from_iso: str, to_iso: str, *, max_pages: int = 2000) -> list:
    """
    Scans and retrieves paginated data from an API within a specified time window.
    Args:
        headers (dict): HTTP headers to include in the API request.
        from_iso (str): ISO 8601 formatted start timestamp for the data window.
        to_iso (str): ISO 8601 formatted end timestamp for the data window.
        max_pages (int, optional): Maximum number of pages to fetch before aborting. Defaults to 2000.
    Returns:
        list: A list of all items retrieved across pages within the specified time window.
    Raises:
        AssertionError: If PAGE_LIMIT is not a positive integer.
        RuntimeError: If pagination appears to be broken (e.g., same page repeating or max_pages exceeded).
    Notes:
        - Uses an `offset`-based pagination strategy.
        - Detects and prevents infinite loops by checking for repeated first item IDs.
        - Stops fetching when an empty page is returned or the last page has fewer items than PAGE_LIMIT.
    """
    out, offset = [], 0
    seen_first_ids = set()
    assert isinstance(PAGE_LIMIT, int) and PAGE_LIMIT > 0, "PAGE_LIMIT must be a positive int"
    for page in range(max_pages):
        page = fetch_page(headers, from_iso, to_iso, offset)
        if not page:
            # empty page → nothing else to fetch
            return out
        # Detect if the same page is being returned repeatedly
        first_id = page[0].get("id") if isinstance(page[0], dict) else None
        if first_id is not None:
            if first_id in seen_first_ids:
                raise RuntimeError(
                    f"Pagination stuck: same first item id {first_id} is repeating. "
                    f"This usually means the API ignores 'offset' or expects a different param."
                )
            seen_first_ids.add(first_id)
        out.extend(page)
        if len(page) < PAGE_LIMIT:
            return out
        offset += PAGE_LIMIT
    raise RuntimeError("Aborting after max_pages – pagination likely broken.")


def is_bort_diskstats(events: dict) -> bool:
    """
      Checks if an event log entry is a Bort_DiskStats event.
      Parameters:
      ev : dict
          Event log entry.

      Returns:
      bool
          True if the event matches Bort_DiskStats criteria.
      """
    event_details = events.get("details") or {}
    search_event = "bort_diskstats"
    search_fields = [
        events.get("type", ""),
        str(event_details.get("Tag", "")),
        str(event_details.get("event_tag_name", "")),
        str(event_details.get("Event Type", "")),
        str(event_details.get("Message", "")),
        str(event_details.get("message", "")),
    ]
    return any(search_event in field.lower() for field in search_fields)


def is_connected_display(events: dict) -> bool:
    """
      Checks if an event log entry is a ConnectedDisplay event.
      Parameters:
      ev : dict
          Event log entry.

      Returns:
      bool
          True if the event matches ConnectedDisplay criteria.
      """
    event_details = events.get("details") or {}
    search_event = "connecteddisplay"
    search_fields = [
        events.get("type", ""),
        str(event_details.get("Tag", "")),
        str(event_details.get("event_tag_name", "")),
        str(event_details.get("Event Type", "")),
        str(event_details.get("Message", "")),
        str(event_details.get("message", "")),
    ]
    return any(search_event in field.lower() for field in search_fields)


def ts_ms_to_ist(ms: int) -> str:
    """
    Converts a timestamp in milliseconds to a formatted IST string.
    Parameters:
    ms : int
        Timestamp in milliseconds since epoch.

    Returns:
    str
        Formatted timestamp string in IST.
    """
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(IST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def normalize_expected_value(expected_value):
    """Normailze expected value(s) to a list of lowercase strings for comparison.
    Parameters:
        expected_value : str | list
            Expected value(s) to normalize.
    Returns:
        list[str]
      """

    if isinstance(expected_value, list):
        return [str(value).lower() for value in expected_value]
    return [str(expected_value).lower()]


def extract_values(log_item, key_name):
    """ Extract the values associated with given key from 'details' section.
     This function searches for both the top-level fields and nested details field within a log dictionary
     to collect all the values that is corresponded to the specified key.It handles the multiple
     data types including strings, lists, tuples, and dictionaries.
    Parameters:
            log_item : dict
            key_name : str

    Returns:
        list[str]
     """
    possible_values = []
    # 1. Direct key from log item
    value = log_item.get(key_name)
    if value is not None:
        if isinstance(value, (list, tuple)):
            possible_values.extend(map(str, value))
        elif isinstance(value, dict):
            possible_values.extend(map(str, value.values()))
        else:
            possible_values.append(str(value))
    # 2. Parse 'details' section
    details = log_item.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            possible_values.append(details)
            details = None
    if isinstance(details, dict):
        # Specific key match
        if key_name in details:
            val = details[key_name]
            if isinstance(val, (list, tuple)):
                possible_values.extend(map(str, val))
            else:
                possible_values.append(str(val))
            # Add all other values
        for val in details.values():
            if isinstance(val, (list, tuple)):
                possible_values.extend(map(str, val))
            else:
                possible_values.append(str(val))
    elif isinstance(details, (list, tuple)):
        possible_values.extend(map(str, details))

        # Remove duplicates and empty strings
    unique_values = [v.strip() for v in dict.fromkeys(possible_values) if v.strip()]
    return unique_values

def is_match(value, expected_patterns):
    """This function checks the a given value matches any of the expected patterns.
         1.It supports Case-insensitive substring checks.
         2.Direct filename or path comparisons.
         3.File extension matching with patterns like '*.ext' or '.ext'.
    Parameter:
        value : str
        Expected_patterns : list[str]
    Returns:
        bool
        """
    value = str(value).lower()
    try:
        path = PurePath(value)
        file_name = path.name.lower()
        extension = path.suffix.lower()
    except Exception:
        file_name, extension = value, ""

    for pattern in expected_patterns:
        if not pattern:
            continue
        if pattern in value or pattern in file_name:
            return True
        if pattern.startswith("*.") and extension == pattern[1:]:
            return True
        if pattern.startswith(".") and extension == pattern:
            return True
        if fnmatch.fnmatch(value, pattern) or fnmatch.fnmatch(file_name, pattern):
            return True
    return False


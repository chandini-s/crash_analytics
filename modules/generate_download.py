"""
generate and download_on_demand bug report via ADB and requests

Triggers an ON-DEMAND bugreport on a Logitech device via ADB, polls the analytics API
for the latest DebugArchive report, and downloads it using a pre-signed URL.

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

Steps:
------
1. Trigger ON-DEMAND bugreport via ADB broadcast.
2. Calls GET /api/bugreports/{DEVICE_ID}?from=..&to=.. to list items.
3. Poll the bugreport API for up to 10 minutes.
4. Filter for ON-DEMAND DebugArchive reports.
5. Download the latest matching report as a ZIP file.

Timezones:
----------
- Timestamps are converted to IST (India Standard Time) for display.
- Downloads and filenames use UTC for consistency.
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
import time, subprocess, re, requests
from utils import get_serial_number,get_selected_device, get_auth_and_cookie

# -----Configuration -----
#DEVICE = get_selected_device()
DEVICE = "10.91.208.243"
DEVICE_ID =get_serial_number(DEVICE)
API_BASE = "https://logi-analytics.vc.logitech.com/api"
LIST_URL = f"{API_BASE}/bugreports/{DEVICE_ID}"
PRESIGN_URL = f"{API_BASE}/bugreports/get-download-url"

# ------Paths -----
ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DOWNLOAD_DIR = ROOT / "downloaded_bugreports"

# ------Timezone & Regex -----
IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc
ISOZ = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def load(p: Path) -> str | None:
    """
    Reads a file and returns its content as a stripped string.
    Parameters:
    -----------
    path : str
        Path to the file.
    Returns:
    --------
    str
        File content without leading/trailing whitespace.
    """
    try:
        file_content = p.read_text(encoding="utf-8").strip()
        return file_content if file_content else None
    except FileNotFoundError:
        return None


def headers(jwt, cookie):
    """
    Constructs HTTP headers for API requests using JWT and cookie.
    Parameters:
    -----------
    jwt : str
        Raw JWT token (no "Bearer" prefix).
    cookie : str
        Full cookie string from DevTools.
    Returns:
    --------
    dict
        Dictionary of headers for requests.
    """
    return {
        "Accept": "application/json, text/plain, */*",
        "authorization": jwt,
        "Cookie": cookie,
        "Content-Type": "application/json; charset=UTF-8",
        "Origin": "https://logi-analytics.vc.logitech.com",
        "Referer": f"https://logi-analytics.vc.logitech.com/device/view/{DEVICE_ID}/Asia%2FCalcutta/bugreports",
        "User-Agent": "Mozilla/5.0"
    }


def iso_z(dt):  # UTC ISO8601 with Z and milliseconds
    """
    Converts a datetime object to ISO8601 UTC format with milliseconds and 'Z' suffix.
    Parameters:
    -----------
    dt : datetime object.
    Returns:
    --------
    str
        ISO8601 UTC string.
    """
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ts_from_item(item: Dict) -> Optional[str]:
    """
    Extracts and converts a timestamp from a bugreport item to IST.
    Parameters:
    -----------
    item : dict - Bugreport item dictionary.
    Returns:
    --------
    Optional[str] - ISO8601 IST timestamp string or None.
    """
    md = item.get("metadata") or {}
    t = md.get("time")
    if isinstance(t, str) and ISOZ.match(t):
        # Convert ISO UTC string to IST
        dt = datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(IST)
        return dt.isoformat()
    if isinstance(item.get("ts"), int):
        # Convert timestamp in milliseconds to IST
        dt = datetime.fromtimestamp(item["ts"] / 1000.0, timezone.utc).astimezone(IST)
        return dt.isoformat()
    return None


def is_on_demand(item: Dict) -> bool:
    """
    Checks if a bugreport item is marked as ON-DEMAND.
    Parameters:
    item : dict
        Bugreport item dictionary.
    Returns:
    bool
        True if ON-DEMAND, False otherwise.
    """
    v = (item.get("metadata") or {}).get("ondemand")
    return (v is True) or (isinstance(v, str) and v.lower() == "true")


def is_periodic(item: Dict) -> bool:
    """
    True for periodic reports: either ondemand == False, or the flag is missing.
    """
    v = (item.get("metadata") or {}).get("ondemand")
    if isinstance(v, bool):
        return not v
    if isinstance(v, str):
        return v.strip().lower() not in ("true", "1", "yes")
    # Treat missing/unknown as periodic
    return True


def presign(header, path):
    """
    Requests a presigned S3 URL for downloading a bugreport archive.
    Parameters:
    -----------
    header : dict
        HTTP headers.
    path : str
        S3 path of the bugreport archive.
    Returns:
    --------
    str
        Presigned download URL.
    """
    response = requests.post(PRESIGN_URL, headers=header, json={"path": path}, timeout=30)
    response.raise_for_status()
    response_json = response.json()
    return response_json.get("url") or response_json.get("signedUrl") or response_json.get("download_url")


def safe_stamp(dt):
    """
    Sanitizes a datetime for use in filenames by removing illegal characters.
    Parameters:
    -----------
    dt : datetime object.
    Returns:
    --------
    str
        Safe string representation of the datetime.
    """
    # make tz-aware and format in UTC, then remove characters not allowed on Windows
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    s = dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return re.sub(r'[:<>\"/\\|?*]+', '-', s)


def download_ondemand_bugreport(signed_url, found_time):
    """
    Downloads the bugreport archive from a presigned URL and saves it to disk.
    Parameters:
    signed_url : str
        Presigned S3 URL.
    found_time : Union[str, datetime]
        Timestamp of the bugreport (used in filename).
    Returns:
    str
        Path to the saved ZIP file.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True) # ensure download directory exists
    if isinstance(found_time, str):
        found_time = datetime.fromisoformat(found_time.replace("Z", "+00:00"))
    name = f"debugarchive_on-demand_{safe_stamp(found_time)}_{safe_stamp(datetime.now(timezone.utc))}.zip"
    output_path = DOWNLOAD_DIR / name
    with requests.get(signed_url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"Saved: {name}")
    return name


def download_periodic_bugreport(signed_url, found_time):
    """
    Downloads the bugreport archive from a presigned URL and saves it to disk.
    Parameters:
    signed_url : str
        Presigned S3 URL.
    found_time : Union[str, datetime]
        Timestamp of the bugreport (used in filename).
    Returns:
    str
        Path to the saved ZIP file.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True) # ensure download directory exists
    if isinstance(found_time, str):
        found_time = datetime.fromisoformat(found_time.replace("Z", "+00:00"))
    name = f"debugarchive_periodic_{safe_stamp(found_time)}_{safe_stamp(datetime.now(timezone.utc))}.zip"
    output_path = DOWNLOAD_DIR / name
    with requests.get(signed_url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"Saved: {name}")
    return name


def trigger_on_demand(adb_id):
    """
    Triggers an ON-DEMAND bugreport on the device via ADB broadcast.
    Parameters:
    adb_id : str
        ADB serial or IP of the device.
    Returns:
    datetime
        Trigger time in IST.
    """
    subprocess.run(f"adb -s {adb_id} root", shell=True, check=False)
    trigger_time = datetime.now(IST)
    cmd = ("adb -s {id} shell am broadcast "
           "-a com.logitech.intent.action.GENERATE_BUG_REPORT "
           "-n com.logitech.crashanalytics/com.memfault.bort.receivers.ControlReceiver").format(id=adb_id)
    subprocess.run(cmd, shell=True, check=True)
    print("Triggered at (IST):", trigger_time.isoformat())
    return trigger_time


def to_aware_utc(dt_or_str):
    # helper in case someone still passes a string
    if isinstance(dt_or_str, str):
        s = dt_or_str.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    else:
        dt = dt_or_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def poll_and_download_ondemand(jwt, cookie, trigger_time, poll_minutes=15, poll_every_sec=60):
    """
    Polls the bugreport API for ON-DEMAND DebugArchive reports and downloads the latest one.
    Parameters:
    -----------
    jwt : str
        Raw JWT token.
    cookie : str
        Full cookie string.
    trigger_utc : datetime
        Time when the bugreport was triggered.
    poll_minutes : int
        Total duration to poll (default: 15 minutes).
    poll_every_sec : int
        Interval between polls (default: 60 seconds).
    Returns:
        None
    """
    request_headers = headers(jwt, cookie)
    poll_start_time = trigger_time - timedelta(minutes=2)  # start a bit earlier to account for clock skew
    poll_end_time = trigger_time + timedelta(minutes=poll_minutes)  # poll window upto poll_minutes after trigger
    attempt = 0
    print("Polling for on-demand reports from", poll_start_time, "to", poll_end_time)
    while True:
        attempt += 1
        now_utc = datetime.now(IST)
        # stop after poll window has fully elapsed
        if now_utc > poll_end_time + timedelta(minutes=1):
            print("Timeout: on-demand report not visible in analytics within window.")
            return

        params = {"from": iso_z(poll_start_time), "to": iso_z(poll_end_time)}
        response = requests.get(LIST_URL, headers=request_headers, params=params, timeout=30)
        print(f"[{attempt}] GET {response.url} -> {response.status_code}")
        if response.status_code == 200:
            report_items = response.json() if isinstance(response.json(), list) else []
            # pick newest ON-DEMAND DebugArchive in window
            matching_reports = []
            for report in report_items:
                if (report.get("metadata", {}).get("reporttag", "") or "").lower() != "debugarchive":
                    continue
                if not is_on_demand(report):
                    continue
                timestamp_str = ts_from_item(report)
                if timestamp_str: matching_reports.append((timestamp_str, report))
            if matching_reports:
                matching_reports.sort(key=lambda x: x[0], reverse=True)
                latest_timestamp, latest_report = matching_reports[0]
                report_path = latest_report.get("path")
                mar_path = (latest_report.get("metadata",{}) or {}).get("path") or ""
                print("Found ON-DEMAND:", latest_timestamp, "path=", report_path)
                url = presign(request_headers, report_path)
                fname = download_ondemand_bugreport(url, datetime.fromisoformat(latest_timestamp.replace("Z", "+00:00")))
                return {"path":mar_path, "saved_as": fname}
        # not found yet
        sleep_left = poll_every_sec
        while sleep_left > 0:
            time.sleep(1)
            sleep_left -= 1
        print()           # newline after progress


def poll_and_download_periodic(jwt, cookie, from_time, to_time, poll_every_sec=60) -> str:
    """
    Poll for a periodic (NOT on-demand) DebugArchive in [from_time, to_time],
    download the newest, and return the saved ZIP path.

    Accepts `from_time`/`to_time` as aware datetimes or ISO strings (IST/UTC).
    Uses UTC internally. Raises TimeoutError if no match appears by the deadline.
    """
    request_headers = headers(jwt, cookie)
    # Normalize inputs to aware UTC
    start_dt = to_aware_utc(from_time)
    end_dt   = to_aware_utc(to_time)

    # Add grace for indexing delay
    deadline = end_dt + timedelta(minutes=15)
    print("Polling for Periodic reports from", start_dt.isoformat(), "to", end_dt.isoformat())
    attempt = 0
    while datetime.now(UTC) <= deadline:
        attempt += 1

        params = {
            "from": iso_z(start_dt),
            "to":   iso_z(end_dt),
        }
        response = requests.get(LIST_URL, headers=request_headers, params=params, timeout=30)
        print(f"[{attempt}] GET {response.url} -> {response.status_code}")

        if response.status_code in (401, 403):
            response.raise_for_status()
        response.raise_for_status()

        data = response.json()
        items = data if isinstance(data, list) else []
        matches = []
        for report in items:
            tag = (report.get("metadata", {}) .get("reporttag") or "").lower()
            if tag != "debugarchive":
                continue
            if not is_periodic(report):
                continue
            ts_str = ts_from_item(report)
            if ts_str:
                matches.append((ts_str, report))
        if matches:
            # newest first; ISO timestamps sort well lexicographically
            matches.sort(key=lambda x: x[0], reverse=True)
            latest_ts_str, latest_report = matches[0]
            report_path = latest_report.get("path", "")
            print("Found Periodic:", latest_ts_str, "path=", report_path)

            url = presign(request_headers, report_path)
            ts_dt = datetime.fromisoformat(latest_ts_str.replace("Z", "+00:00"))
            saved_path = download_periodic_bugreport(url, ts_dt)
            print(f"Saved: {saved_path}")
            return saved_path  # return path so test can assert
        for s in range(poll_every_sec, 0, -1):
            time.sleep(1)
        print()
    raise TimeoutError("Periodic bugreport did not appear within the poll window.")


def main():
    """
     Main entry point:
    - Loads credentials.
    - Triggers ON-DEMAND bugreport.
    - Polls and downloads the report.
    """
    jwt, cookie = get_auth_and_cookie()
    trigger_time = trigger_on_demand(DEVICE)
    to_time = trigger_time + timedelta(minutes=30)
    # poll up to 10 minutes, checking every 60 seconds
    poll_and_download_periodic(jwt, cookie, trigger_time,to_time , poll_every_sec=60)

if __name__ == "__main__":
    """ Run the main function if this script is executed directly. """
    main()
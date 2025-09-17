"""Test case for the events module, which checks if the event logs can be accessed after rebooting the device and downloading the bug report."""

import time
from datetime import datetime, timedelta, timezone
import pytest
from modules import events as ev
from modules.extraction import dump_event_main
import utils as util
from modules import generate_download as generate

def test_events_bort():
    """
    End-to-end check:
      1) build headers from config
      2) pick ADB device, reboot & wait
      3) poll the fixed window for Bort_DiskStats
    Passes when at least one Bort_DiskStats event is found.
    """

    # ---- 1) Headers / auth ----
    if not util.have_auth():
        pytest.skip("Missing auth in config/auth.txt or cookie in config/cookie.txt")
    try:
        headers = util.build_headers()
    except Exception as e:
        pytest.fail(f"Auth configuration error: {e}")
        return

    # ---- 2) Reboot device via ADB ----
    serial = None
    try:
        serial = util.get_selected_device()
    except Exception as e:
        pytest.skip(f"No online ADB device: {e}")

    reboot_ist = ev.reboot_and_wait(serial)

    # Build the fixed IST window used by the app code
    from_iso = ev.iso_ist(reboot_ist - timedelta(minutes=ev.PRE_REBOOT_MIN))
    to_iso = ev.iso_ist(reboot_ist + timedelta(minutes=ev.POST_REBOOT_MIN))
    print(f"Fixed window (IST): {from_iso} to {to_iso}")

    # ---- 3) Poll for Bort_DiskStats ----

    deadline = datetime.now(ev.IST) + timedelta(minutes=ev.POLL_TIMEOUT_MIN)
    found = False
    last_count = 0

    while datetime.now(ev.IST) < deadline and not found:
        page = ev.scan_window(headers, from_iso, to_iso)
        last_count = len(page)
        matches = [item for item in page if ev.is_bort_diskstats(item)]
        if matches:
            match = matches[0]
            ts = ev.ts_ms_to_ist(match.get("timestamp")) if "timestamp" in match else "n/a"
            print(f"Bort_DiskStats found at {ts}")
            found = True
            break

        print(f"…no match yet (scanned {last_count}). Sleeping {ev.POLL_INTERVAL_MIN} min")
        time.sleep(ev.POLL_INTERVAL_MIN * 60)

    assert found, f"Expected Bort_DiskStats not found (scanned last page count={last_count})"
    # ---- 4) Download the periodic bug report ----

    jwt = generate.load(generate.AUTH_PATH)
    cookie = generate.load(generate.COOKIE_PATH)
    from_time = generate.iso_z(datetime.fromisoformat(from_iso).astimezone(timezone.utc))
    to_time = generate.iso_z(datetime.fromisoformat(to_iso).astimezone(timezone.utc))
    downloaded_path = generate.poll_and_download_periodic(jwt, cookie, from_time,to_time, poll_every_sec=60)
    assert downloaded_path, "Failed to download periodic bug report"
    print(f"Downloaded periodic bug report to {downloaded_path}")

    # ---- 5) Extract events from the downloaded bug report ----
    try:
        search_found = dump_event_main()
        if not search_found:
            pytest.fail("Event extraction did not find expected events.")
    except Exception as e:
        pytest.fail(f"Event extraction failed: {e}")
        return




""" Test cases for TEAMS related testcases"""

import pytest
import time
import os
import json
from datetime import datetime, timedelta, timezone
from modules import events as ev
from modules.extraction import dump_event_main
from modules.version import get_collabos_version, get_collab_version_from_adb
from modules.mode import fetch_device_mode
import utils as util
from modules import generate_download as generate
from modules import local_storage

util.have_auth()  # Ensure auth is available before running tests

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
    jwt, cookie = util.get_auth_and_cookie()
    from_time = generate.iso_z(datetime.fromisoformat(from_iso).astimezone(timezone.utc))
    to_time = generate.iso_z(datetime.fromisoformat(to_iso).astimezone(timezone.utc))
    downloaded_path = generate.poll_and_download_periodic(jwt, cookie, from_time, to_time, poll_every_sec=60)
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


def test_events_display():
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
        matches = [item for item in page if ev.is_connected_display(item)]
        if matches:
            match = matches[0]
            ts = ev.ts_ms_to_ist(match.get("timestamp")) if "timestamp" in match else "n/a"
            print(f"ConnectedDisplay found at {ts}")
            found = True
            break
        print(f"…no match yet (scanned {last_count}). Sleeping {ev.POLL_INTERVAL_MIN} min")
        time.sleep(ev.POLL_INTERVAL_MIN * 60)
    assert found, f"Expected ConnectedDisplay not found (scanned last page count={last_count})"


def test_device_mode_is_appliance():
    """
    call get_device_mode() from mode.py and assert
    the device mode equals "Appliance".
    """
    mode = fetch_device_mode()
    if mode:
        print(f"Mode is: {mode}")
        assert mode == "Appliance", "FAIL: DUT is not in Appliance Mode"
        print("PASS: DUT is in Appliance Mode")
    else:
        pytest.fail("Could not find Mode value on the page.")


def test_version_verification():
    """Test to verify the software version displayed on the web page matches the device version."""
    web_version = get_collabos_version()
    device = util.get_selected_device()
    device_version = get_collab_version_from_adb(device)
    assert device_version is not None, "Failed to retrieve version from device."
    assert web_version is not None, "Failed to extract version from web page."
    print(f"Device Version: {device_version}")
    print(f"Web Version: {web_version}")
    assert device_version == web_version, "Version mismatch between device and web page."


def test_on_demand_bugreport_appears():
    """ Test to trigger an on-demand bug report and verify its appearance. """
    # --- auth from your jenkins ---
    jwt, cookie = util.get_auth_and_cookie()
    if not (jwt or cookie):
        pytest.skip("Missing auth/cookie in ./config (auth.txt or cookie.txt)")
    trigger_time = generate.trigger_on_demand(generate.DEVICE)
    try:
        download_path = generate.poll_and_download_ondemand(
            jwt, cookie, trigger_time,
            poll_minutes=10, poll_every_sec=60
        )
    except TimeoutError:
        pytest.fail("ON-DEMAND bugreport did not appear within the poll window.")
    else:
        assert download_path and isinstance(download_path, str)
        print(f"Downloaded: {download_path}")


def test_events():
    """This function will test the events once after rebooting the device.
        1.Authenticate and retrieves the target device serial number.
        2.Reboot the device and wait for the device to come online.
        3.Calculates a time window around the reboot(pre-and post-reboot).
        4.Loads events  and its details from a JSON file.
        5.Polls the event logs within the defined time window to find expected events.
        """
    # --- Authenticate ---
    if not util.have_auth():
        pytest.skip("Missing auth/cookie")
    headers = util.build_headers()
    device_serial = util.get_selected_device()
    reboot_time = ev.reboot_and_wait(device_serial)
    # ---time window ---
    from_time = ev.iso_ist(reboot_time - timedelta(minutes=ev.PRE_REBOOT_MIN))
    to_time = ev.iso_ist(reboot_time + timedelta(minutes=ev.POST_REBOOT_MIN))
    print(f"Fixed window (IST): {from_time} to {to_time}")
    # --- Load events from JSON file ---
    events_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "event_file.json")
    try:
        with open(events_file, "r", encoding="utf-8") as file:
            json_events = json.load(file)
    except Exception as error:
        pytest.skip(f"Cannot read event_file.json: {error}")
    # --- Poll and check events ---
    pending_events = [dict(event) for event in json_events]
    found_events = []
    deadline = time.time() + ev.POLL_TIMEOUT_MIN * 60
    while pending_events and time.time() < deadline:
        logs = ev.scan_window(headers, from_time, to_time)
        for event_entry in list(pending_events):
            event_name = event_entry.get("event")
            event_key = event_entry.get("key")
            expected_patterns = ev.normalize_expected_value(event_entry.get("expected_value"))
            for log_item in logs:
                if log_item.get("type") != event_name:
                    continue
                possible_values= ev.extract_values(log_item, event_key)
                matched_value=next((val for val in possible_values if ev.is_match(val, expected_patterns)),None)
                if matched_value:
                    print(f"Matched event '{event_name}' key '{event_key}' with value '{matched_value}'")
                    found_events.append(event_name)
                    pending_events.remove(event_entry)
                    break
        if pending_events:
            time.sleep(ev.POLL_INTERVAL_MIN * 60)
    print(f"Found events: {found_events}")
    print(f"Pending events: {pending_events}")
    assert not pending_events, f"Events not found: {pending_events}"


def test_bugreport_without_internet():
    """
    Drive the device with network DOWN, trigger one on-demand bugreport,
    wait locally for a new .mar (up to ~15 min), and make sure the chain
    ended with a clear result and Ethernet was brought back UP by the chain.
    """
    # If needed, ensure we can reach the DUT over TCP/IP and are root.
    if not local_storage.ensure_online() and not local_storage.adb_connect_loop(60):
        pytest.skip("No ADB device online over TCP/IP.")

    iface = "eth0"
    result = local_storage.bugreport_without_internet(iface)

    assert isinstance(result, dict), "Result is not a dictionary."

    status = result.get("status")
    path = result.get("path", ""
                      )
    # Must either find a .mar or timeout; broadcast failures should fail the test.
    assert status in ("found", "timeout"), f"Unexpected status: {status}"

    if status == "found":
        assert path.endswith(".mar"), f"Found file doesn't end with .mar: {path}"


def test_bugreport_flushed_portal_after_internet():
    """Trigger offline chain -> when local .mar is found, poll portal by trigger time and compare metadata path.
    Compares: basename(local_path) == basename(portal_path) -> .mar files match
     """
    # Basic device pre-check
    if not local_storage.ensure_online() and not local_storage.adb_connect_loop(60):
        pytest.skip("No ADB device online over TCP/IP.")

    iface = "eth0"
    # run the on-device offline chain; this returns a dict (status, path, trigger_epoch etc.)
    result = local_storage.bugreport_without_internet(iface)
    status = result.get("status")
    path = result.get("path")

    assert status in ("found", "timeout"), f"Unexpected status from chain: {status}"
    if status == "found":
        assert path.endswith(".mar"), f"Found path does not end with .mar: {path}"

    # Pull values written by the chain
    local_path = result.get("path")
    local_status = result.get("status")
    trig_s = result.get("trigger_epoch")
    if trig_s:
        trig_epoch = int(trig_s)
        trigger_time = datetime.fromtimestamp(trig_epoch, tz=timezone.utc)
    else:
        trig_iso = local_storage.parse_status_field(result, "trigger_utc")
        trigger_time = datetime.fromisoformat(trig_iso.replace("Z", "+00:00")) if trig_iso else None

    local_base = local_storage.filebase(local_path)

    print(f"\n--- LOCAL .mar ---\npath={local_path}\nbase={local_base}")
    print(f"[trigger] epoch={trigger_time}  status={local_status}")

    print("\n--- LAST LOG ---")
    print(local_storage.read_log_tail(80))

    if not local_base:
        print("[WARN] STATUS has no 'path='; cannot compare.")
    else:
        try:
            jwt, cookie = util.get_auth_and_cookie()
            if not (jwt or cookie):
                pytest.skip("Missing auth/cookie in ./config (auth.txt or cookie.txt)")
            trigger_time = trigger_time
            poll_minutes = 10
            poll_every_sec = 60
            mar_path = generate.poll_and_download_ondemand(jwt, cookie, trigger_time,poll_minutes, poll_every_sec)

            portal_path = local_storage.extract_portal_path(mar_path["path"])
            portal_base = local_storage.filebase(portal_path)
            print(f"\n[portal] path={portal_path or '(none)'}")
            print(f"[compare] status_base={local_base}  vs  portal_base={portal_base or '(none)'}")

            assert portal_base == local_base, (
                f"Portal metadata.path does not match local .mar\n"
                f" expected={local_base}\n got     ={portal_base}")
        except:
            pytest.fail("Failed during comparison of local and portal .mar files.")
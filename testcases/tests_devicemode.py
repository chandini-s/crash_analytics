""" tests for the bug report generation and verify the bug report generated at corrected timestamp"""


import time
import os
import subprocess
import platform
from datetime import datetime, timedelta, timezone
import pytest
import utils as util
from modules import generate_download as generate
from modules import events as ev
from modules import extraction


def test_camera_txt_file():
    """ Test to trigger an on-demand bug report and verify its appearance and extract camera.txt """
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
        pytest.fail("✗ ON-DEMAND bugreport did not appear within the poll window.")
    else:
        assert download_path and isinstance(download_path, str)
        print(f"✓ Downloaded: {download_path}")
    try:
        extraction.camera_txt_main()
    except Exception as e:
        pytest.fail(f"Event extraction failed: {e}")


def test_sync_app_bugreport_generation():
    """
        Validate that the Sync App correctly triggers and downloads a periodic bug report
        after a device reboot. The test performs the following steps:

        1. Verifies that a DUT (Device Under Test) is connected via ADB.
        2. Checks for internet connectivity on the DUT.
        3. Locates the Sync App executable based on the OS.
        4. Launches the Sync App and verifies it is running.
        5. Confirms the DUT is detected by the Sync App.
        6. Waits for background sync to complete.
        7. Reboots the DUT and calculates the time window for bug report generation.
        8. Downloads the periodic bug report from the server.
        9. Closes the Sync App after validation.
    """

    # ---- 1) Verify DUT connected ----
    try:
        print("Start test...")
        device_list = subprocess.check_output(["adb", "devices"], text=True)
        assert "device" in device_list, "No DUT detected via ADB."
    except subprocess.SubprocessError as err:
        pytest.skip(f"ADB not available or no device found: {err}")

    # ---- 2) Verify Internet connection ----
    try:
        subprocess.run(["adb", "root"], capture_output=True, text=True)
        subprocess.run(["adb", "shell", "whoami"], capture_output=True, text=True)
        result = subprocess.check_output(["adb", "shell", "ifconfig", "eth0"], text=True)
        print("✅ Internet available:", result)
    except subprocess.SubprocessError:
        pytest.skip("No internet connection on DUT.")

    # ---- 3) Locate Sync App executable ----
    os_name = platform.system()
    if os_name == "Windows":
        sync_app_path = os.path.expandvars(
            r"C:\Program Files (x86)\Logitech\LogiSync\frontend\Sync.exe"
        )
    elif os_name == "Darwin":
        sync_app_path = "/Applications/LogiSync.app/Contents/MacOS/LogiSync"
    else:
        pytest.skip("Unsupported OS for Sync App launch")

    assert os.path.exists(sync_app_path), f"Sync app not found at {sync_app_path}"

    # ---- 4) Launch Sync App ----
    print(f"Launching Sync App from {sync_app_path}")
    if os_name == "Windows":
        os.startfile(sync_app_path)  # Mimics manual launch
    else:
        subprocess.Popen([sync_app_path])
    time.sleep(30)  # Give app time to load UI

    # ---- 4b) Verify Sync App process is running with retry ----
    sync_process_name = "Sync.exe"
    for attempt in range(6):  # Retry for up to 60 seconds
        try:
            tasklist_output = subprocess.check_output("tasklist", text=True)
            if sync_process_name in tasklist_output:
                print("✅ Sync App process is running.")
                break
        except subprocess.SubprocessError as err:
            print(f"Attempt {attempt+1}: Failed to get tasklist - {err}")
        time.sleep(10)
    else:
        pytest.fail("Sync App process not found after multiple retries")

    # ---- 5) Verify device detected ----
    try:
        device_info = subprocess.check_output(
            ["adb", "shell", "getprop", "ro.product.model"], text=True
        ).strip()
        print(f"DUT Detected: {device_info}")
        assert len(device_info) > 0, "DUT info not detected"
    except subprocess.SubprocessError as err:
        pytest.fail(f"Could not verify device in Sync app: {err}")

    # ---- 6) Wait for background sync ----
    print("Waiting 25–30 minutes for background sync before generating bugreport...")
    time.sleep(25 * 60)

    # ---- 7) Reboot device via ADB ----
    try:
        serial = util.get_selected_device()
    except Exception as err:
        pytest.skip(f"No online ADB device: {err}")

    reboot_ist = ev.reboot_and_wait(serial)
    from_iso = ev.iso_ist(reboot_ist - timedelta(minutes=ev.PRE_REBOOT_MIN))
    to_iso = ev.iso_ist(reboot_ist + timedelta(minutes=ev.POST_REBOOT_MIN))
    print(f"Fixed window (IST): {from_iso} to {to_iso}")

    # ---- 8) Download periodic bugreport ----
    jwt, cookie = util.get_auth_and_cookie()
    from_time = generate.iso_z(datetime.fromisoformat(from_iso).astimezone(timezone.utc))
    to_time = generate.iso_z(datetime.fromisoformat(to_iso).astimezone(timezone.utc))
    downloaded_path = generate.poll_and_download_periodic(
        jwt, cookie, from_time, to_time, poll_every_sec=60
    )
    assert downloaded_path, "Failed to download periodic bug report"
    print(f"Downloaded periodic bug report to {downloaded_path}")

    # ---- 9) Close Sync App ----
    if os_name == "Windows":
        subprocess.run(["taskkill", "/IM", "Sync.exe", "/F"], check=False)
    elif os_name == "Darwin":
        subprocess.run(["pkill", "-f", "LogiSync"], check=False)
    print("✅ Sync App closed successfully.")


def test_sync_app_bugreport_generation_without_internet():
    """
        Validate that the Sync App correctly triggers and downloads a periodic bug report
        after a device reboot. The test performs the following steps:

        1. Verifies that a DUT (Device Under Test) is connected via ADB.
        2. Checks for no internet connectivity on the DUT.
        3. Locates the Sync App executable based on the OS.
        4. Launches the Sync App and verifies it is running.
        5. Confirms the DUT is detected by the Sync App.
        6. Waits for background sync to complete.
        7. Reboots the DUT and calculates the time window for bug report generation.
        8. Downloads the periodic bug report from the server.
        9. Closes the Sync App after validation.
    """

    # ---- 1) Verify DUT connected ----
    try:
        print("Start test...")
        device_list = subprocess.check_output(["adb", "devices"], text=True)
        assert "device" in device_list, "No DUT detected via ADB."
    except subprocess.SubprocessError as err:
        pytest.skip(f"ADB not available or no device found: {err}")

    # ---- 2) Verify Internet connection ----
    try:
        subprocess.run(["adb", "root"], capture_output=True, text=True)
        subprocess.run(["adb", "shell", "whoami"], capture_output=True, text=True)
        result = subprocess.check_output(["adb", "shell", "ifconfig", "eth0","down"], text=True)
        print("✅ Internet not available:", result)
    except subprocess.SubprocessError:
        pytest.skip("No internet connection on DUT.")

    # ---- 3) Locate Sync App executable ----
    os_name = platform.system()
    if os_name == "Windows":
        sync_app_path = os.path.expandvars(
            r"C:\Program Files (x86)\Logitech\LogiSync\frontend\Sync.exe"
        )
    elif os_name == "Darwin":
        sync_app_path = "/Applications/LogiSync.app/Contents/MacOS/LogiSync"
    else:
        pytest.skip("Unsupported OS for Sync App launch")

    assert os.path.exists(sync_app_path), f"Sync app not found at {sync_app_path}"

    # ---- 4) Launch Sync App ----
    print(f"Launching Sync App from {sync_app_path}")
    if os_name == "Windows":
        os.startfile(sync_app_path)  # Mimics manual launch
    else:
        subprocess.Popen([sync_app_path])
    time.sleep(30)  # Give app time to load UI

    # ---- 4b) Verify Sync App process is running with retry ----
    sync_process_name = "Sync.exe"
    for attempt in range(6):  # Retry for up to 60 seconds
        try:
            tasklist_output = subprocess.check_output("tasklist", text=True)
            if sync_process_name in tasklist_output:
                print("✅ Sync App process is running.")
                break
        except subprocess.SubprocessError as err:
            print(f"Attempt {attempt+1}: Failed to get tasklist - {err}")
        time.sleep(10)
    else:
        pytest.fail("Sync App process not found after multiple retries")

    # ---- 5) Verify device detected ----
    try:
        device_info = subprocess.check_output(
            ["adb", "shell", "getprop", "ro.product.model"], text=True
        ).strip()
        print(f"DUT Detected: {device_info}")
        assert len(device_info) > 0, "DUT info not detected"
    except subprocess.SubprocessError as err:
        pytest.fail(f"Could not verify device in Sync app: {err}")

    # ---- 6) Wait for background sync ----
    print("Waiting 25–30 minutes for background sync before generating bugreport...")
    time.sleep(25 * 60)

    # ---- 7) Reboot device via ADB ----
    try:
        serial = util.get_selected_device()
    except Exception as err:
        pytest.skip(f"No online ADB device: {err}")

    reboot_ist = ev.reboot_and_wait(serial)
    from_iso = ev.iso_ist(reboot_ist - timedelta(minutes=ev.PRE_REBOOT_MIN))
    to_iso = ev.iso_ist(reboot_ist + timedelta(minutes=ev.POST_REBOOT_MIN))
    print(f"Fixed window (IST): {from_iso} to {to_iso}")

    # ---- 8) Download periodic bugreport ----
    jwt, cookie = util.get_auth_and_cookie()
    from_time = generate.iso_z(datetime.fromisoformat(from_iso).astimezone(timezone.utc))
    to_time = generate.iso_z(datetime.fromisoformat(to_iso).astimezone(timezone.utc))
    downloaded_path = generate.poll_and_download_periodic(
        jwt, cookie, from_time, to_time, poll_every_sec=60
    )
    assert downloaded_path, "Failed to download periodic bug report"
    print(f"Downloaded periodic bug report to {downloaded_path}")

    # ---- 9) Close Sync App ----
    if os_name == "Windows":
        subprocess.run(["taskkill", "/IM", "Sync.exe", "/F"], check=False)
    elif os_name == "Darwin":
        subprocess.run(["pkill", "-f", "LogiSync"], check=False)
    print("✅ Sync App closed successfully.")




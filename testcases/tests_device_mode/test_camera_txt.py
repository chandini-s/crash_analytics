""" tests for the bug report generation and verify the bug report generated at corrected timestamp"""

import pytest
from modules import generate_download as generate
from modules.extraction import camera_txt_main
from utils import get_auth_and_cookie

POLL_MINUTES = 10  # how long to keep checking
POLL_EVERY_SEC = 30  # how often to recheck


def test_on_demand_bugreport_appears():
    # --- auth from your config files ---
    jwt, cookie = get_auth_and_cookie()
    # jwt = generate.load(generate.AUTH_PATH)
    # cookie = generate.load(generate.COOKIE_PATH)
    if not (jwt or cookie):
        pytest.skip("Missing auth/cookie in ./config (auth.txt or cookie.txt)")

    # --- trigger via ADB (no download) ---
    trigger_time = generate.trigger_on_demand(generate.DEVICE_ID)

    try:
        download_path = generate.poll_and_download(
            jwt, cookie, trigger_time,
            poll_minutes=10, poll_every_sec=60
        )
    except TimeoutError:
        pytest.fail("✗ ON-DEMAND bugreport did not appear within the poll window.")
    else:
        assert download_path and isinstance(download_path, str)
        print(f"✓ Downloaded: {download_path}")
    # ---- 5) Extract events from the downloaded bug report ----
    try:
        camera_txt_main()
    except Exception as e:
        pytest.fail(f"Event extraction failed: {e}")
        return


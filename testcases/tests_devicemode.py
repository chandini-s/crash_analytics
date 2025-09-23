""" tests for the bug report generation and verify the bug report generated at corrected timestamp"""

import pytest
from modules import generate_download as generate
from modules.extraction import camera_txt_main
from utils import get_auth_and_cookie


def test_on_demand_bugreport_appears():
    """ Test to trigger an on-demand bug report and verify its appearance and extract camera.txt """
    jwt, cookie = get_auth_and_cookie()
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
        camera_txt_main()
    except Exception as e:
        pytest.fail(f"Event extraction failed: {e}")
        return


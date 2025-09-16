"""Test case to verify the device mode is set to 'Appliance'."""

import pytest
from modules.mode import fetch_device_mode
import utils as util


def _have_auth():
    # same config locations used by events.py
    return util.read_text(util.AUTH_PATH) or util.read_text(util.COOKIE_PATH)


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

"""Test case to verify the device mode is set to 'Appliance'."""

import pytest
from modules.mode import fetch_device_mode
import utils as util


util.have_auth()

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

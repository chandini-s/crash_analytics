"""Test case to verify the device software version using Selenium WebDriver."""

from modules.version import get_collabos_version, get_collab_version_from_adb
import utils as util
from utils import get_selected_device

util.have_auth()
def test_version_verification():
    """Test to verify the software version displayed on the web page matches the device version."""
    web_version = get_collabos_version()
    device=get_selected_device()
    device_version = get_collab_version_from_adb(device)

    assert device_version is not None, "Failed to retrieve version from device."
    assert web_version is not None, "Failed to extract version from web page."

    print(f"Device Version: {device_version}")
    print(f"Web Version: {web_version}")

    assert device_version == web_version, "Version mismatch between device and web page."
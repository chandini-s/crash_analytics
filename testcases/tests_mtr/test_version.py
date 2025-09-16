"""Test case to verify the device software version using Selenium WebDriver."""

from modules.version import get_collabos_version, get_collab_version_from_adb
import utils as util


def _have_auth():
    # same config locations used by events.py
    return util.read_text(util.AUTH_PATH) or util.read_text(util.COOKIE_PATH)


def test_version_verification():
    """Test to verify the software version displayed on the web page matches the device version."""
    web_version = get_collabos_version()
    device_version = get_collab_version_from_adb("10.91.231.25")

    assert device_version is not None, "Failed to retrieve version from device."
    assert web_version is not None, "Failed to extract version from web page."

    print(f"Device Version: {device_version}")
    print(f"Web Version: {web_version}")

    assert device_version == web_version, "Version mismatch between device and web page."
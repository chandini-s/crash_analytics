import subprocess
import re
import subprocess
import json
import logging
import time
from pathlib import Path
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent
teams_credentials_path = ROOT / "teams_login_credentials.json"

def click_element(resource_id, device):
    """
    Finds and clicks an element on the device screen using its resource-id.
    """
    try:
        # Step 1: Dump the UI hierarchy using the correct device ID
        subprocess.run(["adb", "-s", device, "shell", "uiautomator", "dump"], check=True)
        subprocess.run(["adb", "-s", device, "pull", "/sdcard/window_dump.xml"], check=True)

        # Step 2: Parse the UI dump
        tree = ET.parse("window_dump.xml")
        root = tree.getroot()

        # Step 3: Locate the element with the specified resource-id
        for node in root.iter("node"):
            if node.attrib.get("resource-id") == resource_id:
                bounds = node.attrib.get("bounds")
                if bounds:
                    # Calculate the center of the element
                    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
                    if match:
                        x = (int(match.group(1)) + int(match.group(3))) // 2
                        y = (int(match.group(2)) + int(match.group(4))) // 2

                        # Tap the calculated coordinates using the correct device ID
                        subprocess.run(["adb", "-s", device, "shell", "input", "tap", str(x), str(y)], check=True)
                        logging.info("Tapped on element with resource-id '%s' "
                                     "at (%d, %d)", resource_id, x, y)
                        return

        logging.error("Element with resource-id '%s' not found.", resource_id)
    except Exception as e:
        logging.error("Error in clicking element with resource-id '%s': %s", resource_id, e)


def input_text(text, device):
    """
    Inputs text into the currently focused element on the device screen.
    """
    try:
        # Use adb to input text using the correct device ID
        subprocess.run(["adb", "-s", device, "shell", "input", "text", text], check=True)
        logging.info("Input text '%s' on device '%s'", text, device)
    except Exception as e:
        logging.error("Error in inputting text '%s': %s", text, e)

def login_to_teams_dut(device, email, password):
    click_element("com.microsoft.skype.teams.ipphone:id/sign_in_on_the_device",device)

    # send the email address
    click_element("com.microsoft.skype.teams.ipphone:id/edit_email",device)
    input_text(email,device)
    click_element("com.microsoft.skype.teams.ipphone:id/sign_in_button",device)
    time.sleep(10)   # wait for the password page to load

    # send the password
    click_element("com.azure.authenticator:id/common_auth_webview",device)
    #click_element("com.microsoft.windowsintune.companyportal:id/common_auth_webview",device)
    input_text(password,device)

    #click signin button
    click_element("idSIButton9",device)
    time.sleep(5)

    # click to register the device
    click_element("idSIButton9",device)

def login_to_teams_atari(device, email, password):
    click_element("com.microsoft.skype.teams.ipphone:id/sign_in_on_the_device", device)

    # send the email address
    click_element("com.microsoft.skype.teams.ipphone:id/edit_email", device)
    input_text(email, device)
    click_element("com.microsoft.skype.teams.ipphone:id/sign_in_button", device)
    time.sleep(10)  # wait for the password page to load

    # send the password
    click_element("com.azure.authenticator:id/common_auth_webview", device)
    # click_element("com.microsoft.windowsintune.companyportal:id/common_auth_webview",device)
    input_text(password, device)

    # click signin button
    click_element("idSIButton9", device)
    time.sleep(10)

    # click to register the device
    click_element("idSIButton9", device)



def read_json(path):
    """ This function loads a JSON file from the specified path and parses it into a Python object
    (e.g., a dictionary or list) using the `json` module."""
    with open(path, mode='r') as file:
        data = json.load(file)
        return data[0] if isinstance(data, list) else data


if __name__ == "__main__":
    credentials = read_json(teams_credentials_path)
    MAIL = credentials.get("mail","").strip()
    PASSWORD = credentials.get("password","").strip()
    meeting_url = credentials.get("teams_meeting_url","").strip()
    DEVICE = "10.91.208.243"
    login_to_teams_dut(DEVICE, MAIL, PASSWORD)
    time.sleep(60) # wait for login to complete
    print(f"Signed in to Teams successfully with {MAIL}.")

    print("Joining Teams meeting...")
    adb_command = (f'adb -s {DEVICE} shell am start -a android.intent.action.VIEW -d '
                   f'"{meeting_url}"')
    subprocess.run(adb_command, shell=True, check=True)
    time.sleep(10)
    print("Joined Teams meeting successfully.")






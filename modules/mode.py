"""
Fetches device mode from Logitech Analytics API.

- Builds headers from local config (via utils.build_headers).
- Calls GET /api/device/{device_id}.
- Extracts device mode from top-level or metadata fields.
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import requests
from utils import build_headers, get_serial_number, get_selected_device

API_BASE = "https://logi-analytics.vc.logitech.com/api"
DEVICE = get_selected_device()
DEVICE_ID = get_serial_number(DEVICE)
REQUEST_TIMEOUT = 30.0


def get_device_info(device_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Call the device endpoint and return parsed JSON."""
    url = f"{API_BASE}/device/{device_id}"
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_device_mode_from_info(info: Dict[str, Any]) -> Optional[str]:
    """
    Extract device mode from the device JSON.
    Common fields: info['metadata']['devicemode'] or info['deviceMode'] etc.
    This tries a few likely keys and returns the first non-empty string.
    """
    # check top-level keys
    for k in ("devicemode", "deviceMode", "device_mode", "deviceModeName", "mode"):
        v = info.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # check metadata dict (many APIs embed details in metadata)
    md = info.get("metadata") or info.get("meta") or {}
    if isinstance(md, dict):
        for k in ("devicemode", "deviceMode", "device_mode", "deviceModeName", "mode"):
            v = md.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def fetch_device_mode(device_id: str = DEVICE_ID) -> Optional[str]:
    """Fetch device mode by calling API and parsing JSON."""
    headers = build_headers()
    info = get_device_info(device_id, headers)
    return get_device_mode_from_info(info)


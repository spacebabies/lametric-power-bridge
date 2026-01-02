"""LaMetric Time egress module - formats and pushes power data via HTTP"""
import asyncio
import logging
import os
import requests
from urllib.parse import urlparse

try:
    from async_upnp_client.search import async_search
except ImportError:
    async_search = None

from sources.base import PowerReading

logger = logging.getLogger(__name__)

# Icon constants
ICON_POWER = 26337  # Drawing power
ICON_SOLAR = 54077  # Feeding power
ICON_STALE = 1059   # Lightning bolt with red slash (no data)

# Configuration
LAMETRIC_API_KEY = os.environ.get("LAMETRIC_API_KEY")
LAMETRIC_URL = os.environ.get("LAMETRIC_URL")

# Discovery state
_discovered_ip = None
_discovery_attempted = False
_warned_no_url = False  # Track if we've already warned about missing URL


async def _discover_lametric(timeout=10.0):
    """
    Discover LaMetric Time device via SSDP.

    Returns IP address of exactly one device, or None if zero or multiple devices found.
    """
    if async_search is None:
        logger.error("async-upnp-client not installed. Run: pip install async-upnp-client")
        return None

    search_target = "urn:schemas-upnp-org:device:LaMetric:1"
    discovered_devices = []

    logger.debug(f"LaMetric: Starting SSDP discovery (timeout: {timeout}s)")

    try:
        async for result in async_search(timeout=timeout, search_target=search_target):
            location = result.get("location")
            if location:
                parsed = urlparse(location)
                ip = parsed.hostname
                if ip and ip not in discovered_devices:
                    discovered_devices.append(ip)
                    logger.debug(f"LaMetric: Found device at {ip}")

    except Exception as e:
        logger.debug(f"LaMetric: SSDP discovery error: {e}")

    # Handle discovery results
    if len(discovered_devices) == 0:
        logger.warning(
            "LaMetric: No devices found via SSDP discovery. "
            "Set LAMETRIC_URL manually in lametric-power-bridge.env"
        )
        return None
    elif len(discovered_devices) == 1:
        logger.info(f"LaMetric: Discovered device at {discovered_devices[0]}")
        return discovered_devices[0]
    else:
        logger.warning(
            f"LaMetric: Found {len(discovered_devices)} devices: {', '.join(discovered_devices)}. "
            "Cannot determine which to use. Set LAMETRIC_URL manually in lametric-power-bridge.env"
        )
        return None


async def _get_lametric_url():
    """
    Get LaMetric URL, with automatic discovery if not configured.

    Returns constructed URL or None if discovery fails/is ambiguous.
    """
    global _discovered_ip, _discovery_attempted

    # If URL explicitly configured, use it (no discovery)
    if LAMETRIC_URL:
        return LAMETRIC_URL

    # If we already discovered an IP, use it
    if _discovered_ip:
        return f"http://{_discovered_ip}:8080/api/v2/device/notifications"

    # Attempt discovery (only once per process lifecycle)
    if not _discovery_attempted:
        _discovery_attempted = True
        logger.info("LaMetric: No URL configured, attempting SSDP discovery...")
        _discovered_ip = await _discover_lametric(timeout=10.0)

        if _discovered_ip:
            return f"http://{_discovered_ip}:8080/api/v2/device/notifications"

    return None


def _make_request_sync(url, payload):
    """
    Synchronous HTTP POST to LaMetric API.
    Called via asyncio.to_thread to avoid blocking.
    """
    r = requests.post(
        url,
        json=payload,
        auth=("dev", LAMETRIC_API_KEY),
        timeout=2
    )
    r.raise_for_status()


async def _retry_with_rediscovery(payload):
    """
    Retry request with re-discovery after connection failure.

    Returns True if retry succeeded, False otherwise.
    """
    global _discovered_ip

    # Only retry if we used discovery (not manual config)
    if not _discovered_ip or LAMETRIC_URL:
        return False

    logger.info("LaMetric: Connection failed, attempting re-discovery...")
    old_ip = _discovered_ip
    _discovered_ip = None  # Clear cache

    new_ip = await _discover_lametric(timeout=10.0)
    if not new_ip:
        return False

    if new_ip != old_ip:
        logger.info(f"LaMetric: Device IP changed: {old_ip} → {new_ip}")
        _discovered_ip = new_ip

    # Retry with new IP
    url = f"http://{_discovered_ip}:8080/api/v2/device/notifications"
    try:
        await asyncio.to_thread(_make_request_sync, url, payload)
        return True
    except Exception as e:
        logger.warning(f"LaMetric: Retry after re-discovery failed: {e}")
        return False


async def send_http_payload(payload):
    """
    Offloads the blocking HTTP request to a thread with discovery support.
    """
    global _warned_no_url

    url = await _get_lametric_url()

    if not url:
        # Only warn once to avoid log spam (discovery already logged the issue)
        if not _warned_no_url:
            _warned_no_url = True
            logger.warning(
                "LaMetric: No URL available. Either discovery failed or found multiple devices. "
                "Configure LAMETRIC_URL manually to proceed."
            )
        return

    if not LAMETRIC_API_KEY:
        logger.warning("LaMetric: LAMETRIC_API_KEY not configured. Skipping push.")
        return

    try:
        await asyncio.to_thread(_make_request_sync, url, payload)

    except requests.exceptions.ConnectionError as e:
        logger.warning(f"LaMetric: Connection failed: {e}")
        # Attempt re-discovery and retry
        await _retry_with_rediscovery(payload)

    except Exception as e:
        logger.warning(f"LaMetric: HTTP POST failed: {e}")


async def push_to_lametric(reading: PowerReading):
    """
    Formats the data and sends it to LaMetric Time.

    Args:
        reading: PowerReading object with power measurement
    """
    power = round(reading.power_watts)

    # Are we importing power, or exporting it?
    if power < 0:
        icon = ICON_SOLAR
    else:
        icon = ICON_POWER

    # If power is more than 10000 W, show in kW with one decimal
    if abs(power) >= 10000:
        power_kw = power / 1000
        text = f"{power_kw:.1f} kW"
    else:
        text = f"{power} W"

    # Build the frame to LaMetric specifications
    payload = {
        "frames": [
            {
                "text": text,
                "icon": icon,
                "index": 0
            }
        ]
    }

    # Offload blocking call to a thread
    await send_http_payload(payload)


async def push_to_lametric_stale():
    """
    Pushes a stale data indicator to LaMetric when no data is received.
    Shows "-- W" with a lightning bolt with red slash icon.
    """
    payload = {
        "frames": [
            {
                "text": "-- W",
                "icon": ICON_STALE,
                "index": 0
            }
        ]
    }

    await send_http_payload(payload)

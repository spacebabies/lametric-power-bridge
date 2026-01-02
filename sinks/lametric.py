"""LaMetric Time egress module - formats and pushes power data via HTTP"""
import asyncio
import logging
import os
import requests
import socket

from sources.base import PowerReading

logger = logging.getLogger(__name__)

# Icon constants
ICON_POWER = 26337  # Drawing power
ICON_SOLAR = 54077  # Feeding power
ICON_STALE = 1059   # Lightning bolt with red slash (no data)

# Configuration
LAMETRIC_API_KEY = os.environ.get("LAMETRIC_API_KEY")
LAMETRIC_URL = os.environ.get("LAMETRIC_URL")

# SSDP Discovery Configuration
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
LAMETRIC_URN = "urn:schemas-upnp-org:device:LaMetric:1"

# M-SEARCH payload for SSDP discovery
M_SEARCH_MSG = "\r\n".join([
    "M-SEARCH * HTTP/1.1",
    f"HOST: {SSDP_ADDR}:{SSDP_PORT}",
    'MAN: "ssdp:discover"',
    "MX: 3",
    f"ST: {LAMETRIC_URN}",
    "",
    ""
]).encode("utf-8")

# Discovery state
_discovered_ip = None
_discovery_attempted = False


class _SSDPDiscoveryProtocol(asyncio.DatagramProtocol):
    """
    SSDP discovery protocol that accepts responses from ANY source port.

    This is required for LaMetric devices which respond from ephemeral ports
    (e.g., 49153) instead of the standard SSDP port 1900.
    """
    def __init__(self, future: asyncio.Future):
        self.future = future
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.transport.sendto(M_SEARCH_MSG, (SSDP_ADDR, SSDP_PORT))
        logger.debug(f"LaMetric: Sent M-SEARCH to {SSDP_ADDR}:{SSDP_PORT}")

    def datagram_received(self, data: bytes, addr: tuple):
        """Accept packets from ANY source port (LaMetric uses port 49153)"""
        try:
            message = data.decode("utf-8", errors="ignore")

            if "HTTP/1.1 200 OK" in message and LAMETRIC_URN in message:
                ip = addr[0]
                logger.info(f"LaMetric: Discovered device at {ip} (responded from port {addr[1]})")

                if not self.future.done():
                    self.future.set_result(ip)
                    self.transport.close()
        except Exception as e:
            logger.debug(f"LaMetric: Error processing SSDP response: {e}")

    def error_received(self, exc):
        logger.debug(f"LaMetric: SSDP protocol error: {exc}")


async def _discover_lametric(timeout=10.0):
    """
    Discover LaMetric Time device via SSDP, ignoring source port restrictions.

    Returns IP address as string, or None if not found.
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    logger.debug(f"LaMetric: Starting SSDP discovery (timeout: {timeout}s)")

    try:
        # Create UDP socket bound to ephemeral port, accepting responses from any source port
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _SSDPDiscoveryProtocol(future),
            local_addr=("0.0.0.0", 0),
            family=socket.AF_INET
        )

        # Wait for result or timeout
        ip_address = await asyncio.wait_for(future, timeout=timeout)
        return ip_address

    except asyncio.TimeoutError:
        logger.warning(
            "LaMetric: No devices found via SSDP discovery. "
            "Set LAMETRIC_URL manually in lametric-power-bridge.env"
        )
        if 'transport' in locals():
            transport.close()
        return None

    except Exception as e:
        logger.debug(f"LaMetric: SSDP discovery error: {e}")
        if 'transport' in locals():
            transport.close()
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
    url = await _get_lametric_url()

    if not url:
        # Debug level - discovery already logged the actual issue at WARNING
        logger.debug(
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

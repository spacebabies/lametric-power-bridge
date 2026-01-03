"""LaMetric Time egress module - formats and pushes power data via HTTP"""
import asyncio
import logging
import os
import requests
import socket
from urllib.parse import urlparse, urlunparse

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

# URL manager instance (initialized on first use)
_url_manager = None


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
        """
        Accept SSDP responses from ANY source port.

        SECURITY NOTE: This deliberately does NOT filter by source port (unlike most
        SSDP libraries which enforce port 1900). Here's why:

        1. LaMetric devices respond from ephemeral ports (e.g., 49153), not port 1900
        2. Filtering by port would break discovery entirely
        3. The security risk is acceptable because:
           - Requires attacker on local network (if LAN is breached, bigger problems exist)
           - Data sent to LaMetric is non-sensitive (power consumption readings)
           - LaMetric API requires authentication (LAMETRIC_API_KEY)
           - Attack window is small (~10 second discovery timeout)

        Port 1900 filtering in libraries protects against SSDP reflection/amplification
        DDoS attacks, but we're the client (not server), so that doesn't apply here.

        An attacker could spoof SSDP responses to redirect traffic, but they would need
        LAN access AND the LaMetric API key to impersonate the device successfully.
        """
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


class LaMetricURLManager:
    """
    Manages LaMetric URL with SSDP autodiscovery support.

    The full LAMETRIC_URL (including widget secret path) is REQUIRED.
    SSDP discovery only replaces the host portion to handle DHCP changes.

    Example LAMETRIC_URL format:
        http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/f3b7537fe7...

    SSDP discovers device IP and replaces ONLY the hostname:
        http://192.168.2.10:8080/api/v2/widget/update/com.lametric.diy.devwidget/f3b7537fe7...
                  ^^^^^ Only this part changes via SSDP

    Everything else (scheme, port, path, widget secret) comes from LAMETRIC_URL.
    """

    def __init__(self, base_url: str):
        """
        Initialize URL manager with required base URL.

        Args:
            base_url: Full LaMetric widget URL including secret path

        Raises:
            ValueError: If base_url is empty or None
        """
        if not base_url:
            raise ValueError(
                "LAMETRIC_URL is required in lametric-power-bridge.env. "
                "Get the full widget URL from the LaMetric Time mobile app"
            )

        self.base_url = base_url
        self.discovered_ip = None
        self.discovery_attempted = False

    async def get_url(self) -> str:
        """
        Get current LaMetric URL with SSDP-discovered IP if available.

        On first call, attempts SSDP discovery. If successful, replaces
        the host in base_url with discovered IP. Otherwise returns base_url as-is.

        Returns:
            LaMetric URL (either with discovered IP or original host)
        """
        # Attempt SSDP discovery on first call
        if not self.discovery_attempted:
            await self._attempt_discovery()

        # Replace host with discovered IP if available
        if self.discovered_ip:
            return self._replace_host(self.base_url, self.discovered_ip)

        return self.base_url

    async def _attempt_discovery(self):
        """Try SSDP discovery once (called automatically on first get_url)"""
        self.discovery_attempted = True
        logger.info("LaMetric: Attempting SSDP discovery to handle DHCP changes...")
        self.discovered_ip = await _discover_lametric(timeout=10.0)

        if self.discovered_ip:
            logger.info(f"LaMetric: SSDP discovered device at {self.discovered_ip}")
        else:
            logger.info("LaMetric: SSDP discovery failed, using configured URL as-is")

    async def rediscover(self) -> str | None:
        """
        Force re-discovery after connection failure.

        Returns:
            New URL with updated IP if successful, None otherwise
        """
        old_ip = self.discovered_ip
        logger.info("LaMetric: Connection failed, attempting re-discovery...")
        self.discovered_ip = await _discover_lametric(timeout=10.0)

        if not self.discovered_ip:
            logger.warning("LaMetric: Re-discovery failed")
            return None

        if self.discovered_ip != old_ip:
            logger.info(f"LaMetric: Device IP changed: {old_ip} → {self.discovered_ip}")

        return self._replace_host(self.base_url, self.discovered_ip)

    def can_rediscover(self) -> bool:
        """Check if re-discovery is possible (i.e., we're using SSDP, not manual URL)"""
        return self.discovered_ip is not None

    @staticmethod
    def _replace_host(url: str, new_ip: str) -> str:
        """
        Replace only the hostname in a URL, preserving everything else.

        THIS IS THE SINGLE PLACE WHERE LAMETRIC URLS ARE CONSTRUCTED.
        SSDP only provides the IP - all paths/secrets come from base_url.

        Args:
            url: Original URL with widget secret path
            new_ip: New IP address from SSDP discovery

        Returns:
            URL with hostname replaced, everything else preserved

        Example:
            url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/abc123"
            new_ip = "192.168.2.10"
            returns "http://192.168.2.10:8080/api/v2/widget/update/com.lametric.diy.devwidget/abc123"
        """
        parsed = urlparse(url)
        port = parsed.port or 8080
        new_netloc = f"{new_ip}:{port}"

        return urlunparse((
            parsed.scheme,
            new_netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment
        ))


def _get_url_manager() -> LaMetricURLManager:
    """Get or create the singleton URL manager instance"""
    global _url_manager

    if _url_manager is None:
        if not LAMETRIC_URL:
            raise ValueError(
                "LAMETRIC_URL is required in lametric-power-bridge.env. "
                "Get the full widget URL from the LaMetric Time mobile app"
            )
        _url_manager = LaMetricURLManager(LAMETRIC_URL)

    return _url_manager


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


async def _retry_with_rediscovery(url_manager: LaMetricURLManager, payload):
    """
    Retry request with re-discovery after connection failure.

    Args:
        url_manager: LaMetricURLManager instance
        payload: JSON payload to send

    Returns:
        True if retry succeeded, False otherwise
    """
    # Only retry if we used SSDP discovery (not manual URL only)
    if not url_manager.can_rediscover():
        logger.debug("LaMetric: Cannot retry with re-discovery (using manual URL)")
        return False

    # Attempt re-discovery and get new URL
    new_url = await url_manager.rediscover()
    if not new_url:
        return False

    # Retry with new URL
    try:
        await asyncio.to_thread(_make_request_sync, new_url, payload)
        return True
    except Exception as e:
        logger.warning(f"LaMetric: Retry after re-discovery failed: {e}")
        return False


async def send_http_payload(payload):
    """
    Offloads the blocking HTTP request to a thread with SSDP discovery support.

    Args:
        payload: JSON payload to send to LaMetric
    """
    if not LAMETRIC_API_KEY:
        logger.warning("LaMetric: LAMETRIC_API_KEY not configured. Skipping push.")
        return

    try:
        # Get URL manager (raises ValueError if LAMETRIC_URL not configured)
        url_manager = _get_url_manager()
        url = await url_manager.get_url()

        # Send request
        await asyncio.to_thread(_make_request_sync, url, payload)

    except ValueError as e:
        # LAMETRIC_URL not configured
        logger.error(f"LaMetric: Configuration error: {e}")
        return

    except requests.exceptions.ConnectionError as e:
        logger.warning(f"LaMetric: Connection failed: {e}")
        # Attempt re-discovery and retry
        await _retry_with_rediscovery(url_manager, payload)

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

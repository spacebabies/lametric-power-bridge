"""Device discovery utilities using mDNS and SSDP"""
import asyncio
import logging
from typing import Optional
from urllib.parse import urlparse

try:
    from zeroconf.asyncio import AsyncZeroconf
    from zeroconf import ServiceBrowser, ServiceListener
except ImportError:
    AsyncZeroconf = None
    ServiceBrowser = None
    ServiceListener = None

try:
    from async_upnp_client.search import async_search
except ImportError:
    async_search = None

logger = logging.getLogger(__name__)


async def discover_homewizard(timeout: float = 10.0) -> Optional[str]:
    """
    Discover HomeWizard P1 Meter via mDNS.

    Searches for _hwenergy._tcp service on local network.

    Args:
        timeout: Discovery timeout in seconds (default: 10.0)

    Returns:
        IP address (str) if found, None otherwise
    """
    if AsyncZeroconf is None or ServiceBrowser is None or ServiceListener is None:
        logger.error("zeroconf library not installed. Run: pip install zeroconf")
        return None

    discovered_ip = None
    found_event = asyncio.Event()

    class HomeWizardListener(ServiceListener):
        """Listener for HomeWizard mDNS services"""

        def add_service(self, zc, type_, name):
            """Called when a service is discovered"""
            asyncio.create_task(self._async_add_service(zc, type_, name))

        async def _async_add_service(self, zc, type_, name):
            """Async handler for service discovery"""
            nonlocal discovered_ip

            try:
                info = await zc.async_get_service_info(type_, name)
                if info:
                    # Extract IP address from service info
                    addresses = info.parsed_addresses()
                    if addresses:
                        discovered_ip = addresses[0]
                        logger.info(f"HomeWizard: Discovered device '{name}' at {discovered_ip}")
                        found_event.set()
            except Exception as e:
                logger.debug(f"HomeWizard: Error getting service info for {name}: {e}")

        def update_service(self, zc, type_, name):
            """Called when service is updated"""
            pass

        def remove_service(self, zc, type_, name):
            """Called when service is removed"""
            pass

    # Start mDNS browsing
    logger.debug(f"HomeWizard: Starting mDNS discovery (timeout: {timeout}s)")

    try:
        async with AsyncZeroconf() as azc:
            listener = HomeWizardListener()
            browser = ServiceBrowser(azc.zeroconf, "_hwenergy._tcp.local.", listener)

            try:
                # Wait for discovery or timeout
                await asyncio.wait_for(found_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.debug(f"HomeWizard: Discovery timed out after {timeout}s")
            finally:
                browser.cancel()
    except Exception as e:
        logger.debug(f"HomeWizard: Discovery error: {e}")

    return discovered_ip


async def discover_lametric(timeout: float = 10.0) -> Optional[str]:
    """
    Discover LaMetric Time device via SSDP.

    Searches for urn:schemas-upnp-org:device:LaMetric:1 device type.

    Args:
        timeout: Discovery timeout in seconds (default: 10.0)

    Returns:
        IP address (str) if found, None otherwise
    """
    if async_search is None:
        logger.error("async-upnp-client library not installed. Run: pip install async-upnp-client")
        return None

    search_target = "urn:schemas-upnp-org:device:LaMetric:1"

    logger.debug(f"LaMetric: Starting SSDP discovery (timeout: {timeout}s)")

    try:
        # Search for LaMetric devices
        async for result in async_search(timeout=timeout, search_target=search_target):
            # Result contains location URL (e.g., http://192.168.1.50:4343/description.xml)
            location = result.get("location")
            if location:
                # Extract IP from location URL
                parsed = urlparse(location)
                ip = parsed.hostname

                if ip:
                    logger.info(f"LaMetric: Discovered device at {ip}")
                    return ip

    except Exception as e:
        logger.debug(f"LaMetric: SSDP discovery error: {e}")

    logger.debug(f"LaMetric: Discovery timed out after {timeout}s")
    return None

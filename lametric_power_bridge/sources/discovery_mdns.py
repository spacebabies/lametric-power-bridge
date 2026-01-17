"""mDNS discovery module for HomeWizard Energy devices"""
import asyncio
import logging
from typing import Optional

from zeroconf import ServiceListener, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

logger = logging.getLogger(__name__)

# Constants
HOMEWIZARD_MDNS_TYPE = "_hwenergy._tcp.local."
TARGET_PRODUCT_TYPE = "HWE-P1"  # P1 Meter


class HomeWizardListener(ServiceListener):
    """
    Listener for Zeroconf service events.
    Captures the first device matching the target product type.
    """
    def __init__(self, aiozc: AsyncZeroconf, target_product_type: str, found_event: asyncio.Event):
        self.aiozc = aiozc
        self.target_product_type = target_product_type
        self.found_event = found_event
        self.found_ip: Optional[str] = None
        self.found_name: Optional[str] = None

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service is discovered."""
        if self.found_event.is_set():
            return
        # Process asynchronously to avoid blocking I/O in the listener callback
        asyncio.create_task(self._async_process_service(type_, name))

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service is removed."""
        pass

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service is updated."""
        pass

    async def _async_process_service(self, type_: str, name: str) -> None:
        """Async processing of the discovered service."""
        if self.found_event.is_set():
            return

        info = await self.aiozc.async_get_service_info(type_, name)
        if not info:
            return

        # Check product type in TXT records
        # Properties are bytes, so we need to decode
        properties = {
            k.decode("utf-8") if isinstance(k, bytes) else k: 
            v.decode("utf-8") if isinstance(v, bytes) else v 
            for k, v in info.properties.items()
        }
        
        product_type = properties.get("product_type")
        
        if product_type == self.target_product_type:
            # Get IP address
            addresses = info.parsed_addresses()
            if addresses:
                self.found_ip = addresses[0]
                self.found_name = name
                logger.info(f"mDNS: Found {self.target_product_type} at {self.found_ip} ({name})")
                self.found_event.set()
        else:
            logger.debug(f"mDNS: Ignored device {name} (Type: {product_type})")


async def discover_homewizard_p1(timeout: float = 10.0) -> Optional[str]:
    """
    Discover the first HomeWizard P1 meter on the local network via mDNS.

    Args:
        timeout: Maximum time to wait for discovery in seconds.

    Returns:
        IP address as string if found, None otherwise.
    """
    logger.info(f"mDNS: Browsing for {TARGET_PRODUCT_TYPE} devices...")
    
    aiozc = AsyncZeroconf()
    found_event = asyncio.Event()
    listener = HomeWizardListener(aiozc, TARGET_PRODUCT_TYPE, found_event)
    browser = AsyncServiceBrowser(aiozc.zeroconf, HOMEWIZARD_MDNS_TYPE, listener)

    try:
        await asyncio.wait_for(found_event.wait(), timeout=timeout)
        return listener.found_ip
    except asyncio.TimeoutError:
        logger.warning(f"mDNS: No {TARGET_PRODUCT_TYPE} device found within {timeout}s")
        return None
    finally:
        # Cleanup
        await aiozc.async_close()

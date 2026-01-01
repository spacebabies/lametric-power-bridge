"""LaMetric Time egress module - formats and pushes power data via HTTP"""
import asyncio
import logging
import os
import requests
from typing import Optional

from sources.base import PowerReading
from sources.discovery import discover_lametric

logger = logging.getLogger(__name__)

# Icon constants
ICON_POWER = 26337  # Drawing power
ICON_SOLAR = 54077  # Feeding power
ICON_STALE = 1059   # Lightning bolt with red slash (no data)


class LaMetricSink:
    """
    LaMetric Time sink with automatic discovery.

    Discovers device via SSDP if URL not provided.
    Handles IP changes during runtime.
    """

    def __init__(
        self,
        api_key: str,
        url: Optional[str] = None,
        discovery_timeout: float = 10.0
    ):
        """
        Initialize LaMetric sink.

        Args:
            api_key: LaMetric API key (required)
            url: Push URL (optional, will auto-discover if not provided)
            discovery_timeout: Device discovery timeout (default: 10.0)
        """
        if not api_key:
            raise ValueError("LAMETRIC_API_KEY is required")

        self.api_key = api_key
        self.url = url
        self.discovery_timeout = discovery_timeout
        self._discovered_ip: Optional[str] = None

    async def _ensure_url(self) -> bool:
        """
        Ensure we have a valid LaMetric URL.

        Discovers device if URL not configured.
        Returns True if URL available, False otherwise.
        """
        # If URL already configured, we're done
        if self.url:
            return True

        # If we already discovered an IP, construct URL
        if self._discovered_ip:
            self.url = self._construct_url(self._discovered_ip)
            return True

        # Attempt discovery
        logger.info("LaMetric: No URL configured, attempting discovery...")
        discovered_ip = await discover_lametric(timeout=self.discovery_timeout)

        if not discovered_ip:
            logger.error(
                "LaMetric: Discovery failed. No device found on network. "
                "Set LAMETRIC_URL manually if device is not broadcasting SSDP."
            )
            return False

        self._discovered_ip = discovered_ip
        self.url = self._construct_url(discovered_ip)
        logger.info(f"LaMetric: Discovered device at {discovered_ip}")
        return True

    def _construct_url(self, ip: str) -> str:
        """Construct push URL from discovered IP"""
        # LaMetric push endpoint (v2 API on port 8080 for local access)
        return f"http://{ip}:8080/api/v2/device/notifications"

    async def _perform_http_request(self, payload: dict) -> bool:
        """
        Execute HTTP POST to LaMetric.

        Returns:
            True if successful, False otherwise
        """
        if not await self._ensure_url():
            return False

        try:
            # Use asyncio.to_thread for blocking requests library
            def _sync_request():
                r = requests.post(
                    self.url,
                    json=payload,
                    auth=("dev", self.api_key),
                    timeout=2
                )
                r.raise_for_status()

            await asyncio.to_thread(_sync_request)
            return True

        except requests.exceptions.ConnectionError as e:
            logger.warning(f"LaMetric: Connection failed: {e}")

            # If we discovered this IP, try re-discovery
            if self._discovered_ip:
                logger.info("LaMetric: Attempting re-discovery...")
                self._discovered_ip = None  # Force re-discovery
                self.url = None

                # Retry once with re-discovery
                if await self._ensure_url():
                    try:
                        def _sync_request_retry():
                            r = requests.post(
                                self.url,
                                json=payload,
                                auth=("dev", self.api_key),
                                timeout=2
                            )
                            r.raise_for_status()

                        await asyncio.to_thread(_sync_request_retry)
                        return True
                    except Exception as retry_e:
                        logger.warning(f"LaMetric: Retry after re-discovery failed: {retry_e}")
                        return False

            return False

        except Exception as e:
            logger.warning(f"LaMetric: HTTP POST failed: {e}")
            return False

    async def push(self, reading: PowerReading):
        """
        Format and push power reading to LaMetric.

        Args:
            reading: PowerReading object with power measurement
        """
        power = round(reading.power_watts)

        # Select icon based on import/export
        icon = ICON_SOLAR if power < 0 else ICON_POWER

        # Format text (kW for values >= 10000 W)
        if abs(power) >= 10000:
            text = f"{power / 1000:.1f} kW"
        else:
            text = f"{power} W"

        payload = {
            "frames": [
                {
                    "text": text,
                    "icon": icon,
                    "index": 0
                }
            ]
        }

        await self._perform_http_request(payload)

    async def push_stale(self):
        """Push stale data indicator to LaMetric"""
        payload = {
            "frames": [
                {
                    "text": "-- W",
                    "icon": ICON_STALE,
                    "index": 0
                }
            ]
        }

        await self._perform_http_request(payload)


# Backwards compatibility: Global instance pattern
_sink_instance: Optional[LaMetricSink] = None


def _get_sink() -> LaMetricSink:
    """Get or create global sink instance"""
    global _sink_instance

    if _sink_instance is None:
        api_key = os.environ.get("LAMETRIC_API_KEY")
        url = os.environ.get("LAMETRIC_URL")

        if not api_key:
            raise ValueError("LAMETRIC_API_KEY not configured")

        _sink_instance = LaMetricSink(api_key=api_key, url=url)

    return _sink_instance


async def push_to_lametric(reading: PowerReading):
    """Backwards compatible function wrapper"""
    sink = _get_sink()
    await sink.push(reading)


async def push_to_lametric_stale():
    """Backwards compatible function wrapper"""
    sink = _get_sink()
    await sink.push_stale()

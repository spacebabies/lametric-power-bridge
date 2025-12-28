"""HomeWizard P1 Meter v1 API ingress module - polls power data via HTTP"""
import asyncio
import logging
import sys
from typing import AsyncIterator

try:
    import httpx
except ImportError:
    httpx = None

from sources.base import PowerReading

logger = logging.getLogger(__name__)


class HomeWizardP1Source:
    """
    HomeWizard P1 Meter (v1 API) power source.

    Polls the local HTTP API at regular intervals to retrieve
    real-time power measurements from the smart meter.

    Uses keep-alive connections for efficiency and implements
    retry logic for device busy states.
    """

    def __init__(
        self,
        host: str,
        poll_interval: float = 1.0,
        timeout: float = 5.0,
        max_retries: int = 3
    ):
        """
        Initialize HomeWizard P1 source.

        Args:
            host: IP address or hostname of the P1 Meter (e.g., "192.168.2.87")
            poll_interval: Seconds between polls (default: 1.0)
            timeout: HTTP request timeout in seconds (default: 5.0)
            max_retries: Maximum consecutive retries on errors (default: 3)
        """
        if httpx is None:
            logger.error("httpx library not installed. Run: pip install httpx")
            sys.exit(1)

        self.host = host
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = f"http://{host}/api/v1/data"
        self.client = None

    async def connect(self) -> None:
        """
        Phase 1: HTTP Bootstrap.
        Validates connectivity to the P1 Meter and creates persistent client.
        """
        if not self.host:
            logger.error("HOMEWIZARD_P1_HOST not configured")
            sys.exit(1)
            return  # For test mocking: prevent further execution

        # Create persistent HTTP client with keep-alive
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=1)
        )

        # Test connectivity with a single request
        try:
            logger.info(f"HomeWizard P1: Testing connection to {self.base_url}")
            response = await self.client.get(self.base_url)
            response.raise_for_status()

            data = response.json()

            # Validate that we got power data
            if "active_power_w" not in data:
                logger.warning(
                    "HomeWizard P1: Response missing 'active_power_w' field. "
                    "Device may not be a P1 Meter or is not receiving data from smart meter."
                )
            else:
                logger.info(
                    f"HomeWizard P1: Connection successful. "
                    f"Current power: {data['active_power_w']} W"
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"HomeWizard P1: HTTP error {e.response.status_code}: {e}")
            await self.client.aclose()
            sys.exit(1)
            return
        except httpx.ConnectError:
            logger.error(f"HomeWizard P1: Cannot connect to {self.host}. Check IP address and network.")
            await self.client.aclose()
            sys.exit(1)
            return
        except Exception as e:
            logger.error(f"HomeWizard P1: Bootstrap failed: {e}")
            await self.client.aclose()
            sys.exit(1)
            return

    async def stream(self) -> AsyncIterator[PowerReading]:
        """
        Phase 2: HTTP Polling Stream.

        Polls the /api/v1/data endpoint at regular intervals.
        Yields PowerReading objects as data arrives.

        Handles device busy states (429, 503) with exponential backoff
        and implements auto-retry for transient errors.
        """
        if self.client is None:
            logger.error("HomeWizard P1: stream() called before connect()")
            return

        consecutive_errors = 0
        retry_delay = self.poll_interval

        logger.info(f"HomeWizard P1: Starting polling (interval: {self.poll_interval}s)")

        while True:
            try:
                response = await self.client.get(self.base_url)

                # Handle device busy states
                if response.status_code in (429, 503):
                    consecutive_errors += 1
                    retry_delay = min(self.poll_interval * (2 ** consecutive_errors), 30)
                    logger.warning(
                        f"HomeWizard P1: Device busy (HTTP {response.status_code}). "
                        f"Retrying in {retry_delay:.1f}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    continue

                response.raise_for_status()
                data = response.json()

                # Extract power reading
                active_power = data.get("active_power_w")

                if active_power is not None:
                    # Reset error counter on success
                    consecutive_errors = 0
                    retry_delay = self.poll_interval

                    yield PowerReading(
                        power_watts=float(active_power),
                        timestamp=None  # v1 API doesn't provide timestamps
                    )
                else:
                    logger.debug(
                        "HomeWizard P1: 'active_power_w' field not in response "
                        "(device may be initializing)"
                    )

                # Wait before next poll
                await asyncio.sleep(self.poll_interval)

            except httpx.HTTPStatusError as e:
                consecutive_errors += 1
                if consecutive_errors >= self.max_retries:
                    logger.error(
                        f"HomeWizard P1: Max retries ({self.max_retries}) exceeded. "
                        f"Last error: HTTP {e.response.status_code}"
                    )
                    break

                retry_delay = min(self.poll_interval * (2 ** consecutive_errors), 30)
                logger.warning(
                    f"HomeWizard P1: HTTP error {e.response.status_code}. "
                    f"Retrying in {retry_delay:.1f}s... ({consecutive_errors}/{self.max_retries})"
                )
                await asyncio.sleep(retry_delay)

            except httpx.ConnectError:
                consecutive_errors += 1
                if consecutive_errors >= self.max_retries:
                    logger.error(
                        f"HomeWizard P1: Max retries ({self.max_retries}) exceeded. "
                        "Cannot reach device."
                    )
                    break

                retry_delay = min(self.poll_interval * (2 ** consecutive_errors), 30)
                logger.warning(
                    f"HomeWizard P1: Connection lost. "
                    f"Retrying in {retry_delay:.1f}s... ({consecutive_errors}/{self.max_retries})"
                )
                await asyncio.sleep(retry_delay)

            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= self.max_retries:
                    logger.error(f"HomeWizard P1: Max retries exceeded. Last error: {e}")
                    break

                retry_delay = min(self.poll_interval * (2 ** consecutive_errors), 30)
                logger.error(
                    f"HomeWizard P1: Unexpected error: {e}. "
                    f"Retrying in {retry_delay:.1f}s... ({consecutive_errors}/{self.max_retries})"
                )
                await asyncio.sleep(retry_delay)

        # Cleanup on exit
        if self.client:
            await self.client.aclose()
            logger.info("HomeWizard P1: Client closed")

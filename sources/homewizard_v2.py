"""HomeWizard v2 API ingress module - streams power data via WebSocket"""
import asyncio
import json
import logging
import ssl
import sys
from typing import AsyncIterator, Optional

try:
    import websockets
except ImportError:
    websockets = None

from sources.base import PowerReading
from sources.discovery import discover_homewizard

logger = logging.getLogger(__name__)


class HomeWizardV2Source:
    """
    HomeWizard v2 API power source.

    Connects to the local WebSocket API to stream real-time power
    measurements from the smart meter.

    Requires firmware >= 6.0 and a manually created local user token.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        token: Optional[str] = None,
        discovery_timeout: float = 10.0
    ):
        """
        Initialize HomeWizard v2 source.

        Args:
            host: IP address or hostname (optional, will auto-discover if not provided)
            token: Local user authentication token (required)
            discovery_timeout: Device discovery timeout in seconds (default: 10.0)
        """
        if websockets is None:
            logger.error("websockets library not installed. Run: pip install websockets")
            sys.exit(1)

        self.host = host
        self.token = token
        self.discovery_timeout = discovery_timeout
        # v2 API uses WSS (WebSocket Secure) on port 443
        self.ws_url = f"wss://{host}/api/ws" if host else None

        # Create SSL context that ignores cert verification
        # (HomeWizard uses self-signed certs with non-standard hostnames)
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    async def __aenter__(self):
        """Context manager entry: connect to device"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: no cleanup needed (websockets handles it)"""
        pass

    async def connect(self) -> None:
        """
        Phase 1: Discovery + Validation.

        Discovers device if host not provided, then validates configuration.
        """
        # If no host provided, discover via mDNS
        if not self.host:
            logger.info("HomeWizard v2: No host configured, attempting discovery...")
            discovered_ip = await discover_homewizard(timeout=self.discovery_timeout)

            if not discovered_ip:
                logger.error(
                    "HomeWizard v2: Discovery failed. No device found on network. "
                    "Set HOMEWIZARD_HOST manually if device is not broadcasting mDNS."
                )
                sys.exit(1)
                return  # For test mocking: prevent further execution

            self.host = discovered_ip
            logger.info(f"HomeWizard v2: Discovered device at {self.host}")

        # Construct WebSocket URL now that we have a host
        self.ws_url = f"wss://{self.host}/api/ws"

        if not self.token:
            logger.error("HOMEWIZARD_TOKEN not configured")
            sys.exit(1)

        logger.info(f"HomeWizard v2: Prepared WebSocket connection to {self.ws_url}")

    async def stream(self) -> AsyncIterator[PowerReading]:
        """
        Phase 2: WebSocket Stream with Re-discovery.

        Connects to the device WebSocket, authenticates, subscribes to
        measurement updates, and yields PowerReading objects as they arrive.

        Handles auto-reconnect and re-discovery on persistent connection loss.
        """
        logger.info(f"HomeWizard v2: Connecting to {self.ws_url}")

        consecutive_failures = 0
        max_failures = 3

        # WebSocket auto-reconnect loop
        async for websocket in websockets.connect(
            self.ws_url,
            ssl=self.ssl_context
        ):
            try:
                # --- STEP A: Wait for Authorization Request ---
                # Device initiates by asking for credentials
                auth_request = await websocket.recv()
                msg = json.loads(auth_request)

                if msg.get("type") != "authorization_requested":
                    logger.error(
                        f"HomeWizard v2: Expected 'authorization_requested', got: {msg.get('type')}"
                    )
                    await asyncio.sleep(5)
                    continue

                api_version = msg.get("data", {}).get("api_version", "unknown")
                logger.info(f"HomeWizard v2: Device requests authorization (API {api_version})")

                # --- STEP B: Send Token ---
                auth_msg = {
                    "type": "authorization",
                    "data": self.token
                }
                await websocket.send(json.dumps(auth_msg))

                # --- STEP C: Wait for Authorization Confirmation ---
                auth_response = await websocket.recv()
                resp_msg = json.loads(auth_response)

                if resp_msg.get("type") == "authorized":
                    logger.info("HomeWizard v2: Authentication successful")
                elif resp_msg.get("type") == "error":
                    error_msg = resp_msg.get("data", {}).get("error", "Unknown error")
                    logger.error(f"HomeWizard v2: Authentication failed: {error_msg}")
                    await asyncio.sleep(5)
                    continue
                else:
                    logger.error(
                        f"HomeWizard v2: Unexpected auth response: {resp_msg.get('type')}"
                    )
                    await asyncio.sleep(5)
                    continue

                # --- STEP D: Subscribe to Measurement Updates ---
                subscribe_msg = {
                    "type": "subscribe",
                    "data": "measurement"
                }
                await websocket.send(json.dumps(subscribe_msg))
                logger.info("HomeWizard v2: Subscribed to measurement updates")

                # --- STEP E: Data Loop ---
                async for message in websocket:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    # Debug: log all received messages
                    logger.debug(f"HomeWizard v2: Received message type: {msg_type}, data: {data}")

                    if msg_type == "measurement":
                        # Power data arrives in the "data" field
                        payload = data.get("data", {})
                        # v2 API uses "power_w" (not "active_power_w" like v1)
                        power = payload.get("power_w")

                        if power is not None:
                            # Also extract timestamp from v2 API (it does provide it!)
                            timestamp = payload.get("timestamp")
                            yield PowerReading(
                                power_watts=float(power),
                                timestamp=timestamp
                            )
                        else:
                            logger.debug(
                                "HomeWizard v2: Measurement missing 'power_w' field "
                                "(device may be initializing)"
                            )

                    elif msg_type == "error":
                        error_data = data.get("data", {})
                        logger.error(f"HomeWizard v2: Stream error: {error_data}")

                    else:
                        # Ignore unknown message types (device info, system updates, etc.)
                        logger.debug(f"HomeWizard v2: Ignoring message type: {msg_type}")

                # Reset failure counter on successful connection
                consecutive_failures = 0

            except websockets.ConnectionClosed as e:
                consecutive_failures += 1
                logger.warning(
                    f"HomeWizard v2: Connection closed: {e}. "
                    f"Failure {consecutive_failures}/{max_failures}"
                )

                # After 3 failures, try re-discovery (IP might have changed)
                if consecutive_failures >= max_failures:
                    logger.warning("HomeWizard v2: Attempting re-discovery...")
                    discovered_ip = await discover_homewizard(timeout=self.discovery_timeout)

                    if discovered_ip and discovered_ip != self.host:
                        logger.info(
                            f"HomeWizard v2: Device IP changed: {self.host} → {discovered_ip}"
                        )
                        self.host = discovered_ip
                        self.ws_url = f"wss://{self.host}/api/ws"
                        consecutive_failures = 0  # Reset counter after re-discovery
                    elif discovered_ip == self.host:
                        logger.debug("HomeWizard v2: Re-discovery found same IP")

                logger.info("HomeWizard v2: Reconnecting in 5s...")
                await asyncio.sleep(5)
                continue

            except Exception as e:
                consecutive_failures += 1
                logger.error(
                    f"HomeWizard v2: Unexpected error: {e}. "
                    f"Failure {consecutive_failures}/{max_failures}"
                )

                # Try re-discovery after persistent failures
                if consecutive_failures >= max_failures:
                    logger.warning("HomeWizard v2: Attempting re-discovery...")
                    discovered_ip = await discover_homewizard(timeout=self.discovery_timeout)

                    if discovered_ip and discovered_ip != self.host:
                        logger.info(
                            f"HomeWizard v2: Device IP changed: {self.host} → {discovered_ip}"
                        )
                        self.host = discovered_ip
                        self.ws_url = f"wss://{self.host}/api/ws"
                        consecutive_failures = 0

                logger.info("HomeWizard v2: Reconnecting in 5s...")
                await asyncio.sleep(5)
                continue

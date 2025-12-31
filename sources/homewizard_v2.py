"""HomeWizard v2 API ingress module - streams power data via WebSocket"""
import asyncio
import json
import logging
import sys
from typing import AsyncIterator

try:
    import websockets
except ImportError:
    websockets = None

from sources.base import PowerReading

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
        host: str,
        token: str,
        use_ssl: bool = False
    ):
        """
        Initialize HomeWizard v2 source.

        Args:
            host: IP address or hostname of the device (e.g., "192.168.2.87")
            token: Local user authentication token
            use_ssl: Use wss:// instead of ws:// (default: False for local devices)
        """
        if websockets is None:
            logger.error("websockets library not installed. Run: pip install websockets")
            sys.exit(1)

        self.host = host
        self.token = token
        self.use_ssl = use_ssl
        protocol = "wss" if use_ssl else "ws"
        self.ws_url = f"{protocol}://{host}/api/ws"

    async def __aenter__(self):
        """Context manager entry: connect to device"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: no cleanup needed (websockets handles it)"""
        pass

    async def connect(self) -> None:
        """
        Phase 1: Validation.

        For v2 API, the WebSocket itself handles all bootstrapping.
        This method exists to maintain PowerSource protocol compatibility.
        """
        if not self.host:
            logger.error("HOMEWIZARD_HOST not configured")
            sys.exit(1)

        if not self.token:
            logger.error("HOMEWIZARD_TOKEN not configured")
            sys.exit(1)

        logger.info(f"HomeWizard v2: Prepared WebSocket connection to {self.ws_url}")

    async def stream(self) -> AsyncIterator[PowerReading]:
        """
        Phase 2: WebSocket Stream.

        Connects to the device WebSocket, authenticates, subscribes to
        measurement updates, and yields PowerReading objects as they arrive.

        Handles auto-reconnect on connection loss.
        """
        logger.info(f"HomeWizard v2: Connecting to {self.ws_url}")

        # WebSocket auto-reconnect loop
        async for websocket in websockets.connect(
            self.ws_url,
            # HomeWizard uses self-signed cert for wss, disable verification
            ssl=False if self.use_ssl else None
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

                    if msg_type == "measurement":
                        # Power data arrives in the "data" field
                        payload = data.get("data", {})
                        active_power = payload.get("active_power_w")

                        if active_power is not None:
                            yield PowerReading(
                                power_watts=float(active_power),
                                timestamp=None  # v2 API doesn't provide timestamps in measurements
                            )
                        else:
                            logger.debug(
                                "HomeWizard v2: Measurement missing 'active_power_w' field "
                                "(device may be initializing)"
                            )

                    elif msg_type == "error":
                        error_data = data.get("data", {})
                        logger.error(f"HomeWizard v2: Stream error: {error_data}")

                    else:
                        # Ignore unknown message types (device info, system updates, etc.)
                        logger.debug(f"HomeWizard v2: Ignoring message type: {msg_type}")

            except websockets.ConnectionClosed as e:
                logger.warning(f"HomeWizard v2: Connection closed: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
                continue
            except Exception as e:
                logger.error(f"HomeWizard v2: Unexpected error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
                continue

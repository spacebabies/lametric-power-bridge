"""Tibber ingress module - streams power data via GraphQL WebSocket"""
import asyncio
import json
import logging
import sys
import requests
import websockets
from typing import AsyncIterator

from sources.base import PowerReading

logger = logging.getLogger(__name__)


class TibberSource:
    """
    Tibber Pulse power source.

    Connects to Tibber GraphQL API via WebSocket subscription
    to stream real-time power measurements.
    """

    def __init__(
        self,
        token: str,
        endpoint: str = "https://api.tibber.com/v1-beta/gql",
        user_agent: str = "SpaceBabies-Tibber-Bridge/0.0.1"
    ):
        """
        Initialize Tibber source.

        Args:
            token: Tibber API token
            endpoint: GraphQL HTTP endpoint for bootstrap
            user_agent: User-Agent header for requests
        """
        self.token = token
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.wss_url = None
        self.home_id = None

    async def connect(self) -> None:
        """
        Phase 1: HTTP Bootstrap.
        Fetch both the WebSocket URL and homes with real-time meter.
        """
        if not self.token:
            logger.error("TIBBER_TOKEN not found.")
            sys.exit(1)

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent
        }

        query = """
        {
          viewer {
            websocketSubscriptionUrl
            homes {
              id
              appNickname
              features {
                realTimeConsumptionEnabled
              }
            }
          }
        }
        """

        try:
            response = requests.post(
                self.endpoint,
                json={"query": query},
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"HTTP Bootstrap failed: {e}")
            sys.exit(1)

        viewer = data.get('data', {}).get('viewer', {})
        self.wss_url = viewer.get('websocketSubscriptionUrl')
        homes = viewer.get('homes', [])

        # Find the first home with an active Pulse
        for home in homes:
            if home.get('features', {}).get('realTimeConsumptionEnabled'):
                self.home_id = home['id']
                logger.info(f"Found home: {home.get('appNickname') or 'Home'} ({self.home_id})")
                break

        if not self.wss_url:
            logger.error("Tibber API: No WebSocket URL received.")
            sys.exit(1)

        if not self.home_id:
            logger.error("Tibber API: No home with Pulse found (realTimeConsumptionEnabled=True).")
            sys.exit(1)

    async def stream(self) -> AsyncIterator[PowerReading]:
        """
        Phase 2: WebSocket Stream (graphql-transport-ws protocol).

        Yields PowerReading objects as data arrives from Tibber.
        Handles auto-reconnect internally.
        """
        sub_query = f"""
        subscription {{
          liveMeasurement(homeId: "{self.home_id}") {{
            timestamp
            power
          }}
        }}
        """

        # Protocol headers
        # Note: Tibber requires 'graphql-transport-ws' subprotocol.
        # Also add Token to the connection payload (see init_msg).

        logger.info(f"Tibber API: Connect WebSocket {self.wss_url}")

        async for websocket in websockets.connect(
            self.wss_url,
            subprotocols=["graphql-transport-ws"],
            additional_headers={"User-Agent": self.user_agent}
        ):
            try:
                # --- STEP A: Connection Init ---
                # We are required to introduce ourselves.
                init_msg = {
                    "type": "connection_init",
                    "payload": {"token": self.token}
                }
                await websocket.send(json.dumps(init_msg))

                # --- STEP B: Wait for Ack ---
                # We may only subscribe when we receive a 'connection_ack'.
                while True:
                    resp = await websocket.recv()
                    msg = json.loads(resp)
                    if msg.get("type") == "connection_ack":
                        logger.info("Tibber API: Authentication passed (connection_ack).")
                        break
                    elif msg.get("type") == "connection_error":
                        logger.error(f"Tibber API: Authenticatie error: {msg}")
                        return

                # --- STEP C: Subscribe ---
                # Now we send the actual request for data.
                # ID has to be unique for this session.
                sub_msg = {
                    "id": "1",
                    "type": "subscribe",
                    "payload": {
                        "query": sub_query
                    }
                }
                await websocket.send(json.dumps(sub_msg))
                logger.info("Tibber API: Subscription started. Waiting for data...")

                # --- STEP D: Data Loop ---
                async for message in websocket:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "next":
                        # This has our data
                        payload = data.get("payload", {}).get("data", {}).get("liveMeasurement", {})
                        power = payload.get("power")
                        timestamp = payload.get("timestamp")

                        if power is not None:
                            yield PowerReading(power_watts=power, timestamp=timestamp)

                    elif msg_type == "error":
                        logger.error(f"Tibber API: Stream error: {data}")

                    elif msg_type == "complete":
                        logger.info("Tibber API: Server stopped the stream.")
                        break

            except websockets.ConnectionClosed as e:
                logger.warning(f"Tibber API: Connection closed: {e}. Restarting in 5s...")
                await asyncio.sleep(5)
                continue
            except Exception as e:
                logger.error(f"Tibber API: Unexpected error: {e}")
                await asyncio.sleep(5)

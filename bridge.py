import asyncio
import json
import logging
import os
import sys
import requests
import websockets

from dotenv import load_dotenv

load_dotenv("tibber.env")

# --- Configuration ---
TIBBER_TOKEN = os.environ.get("TIBBER_TOKEN")
TIBBER_ENDPOINT = "https://api.tibber.com/v1-beta/gql"
LAMETRIC_API_KEY = os.environ.get("LAMETRIC_API_KEY")
LAMETRIC_URL = os.environ.get("LAMETRIC_URL")
USER_AGENT = "SpaceBabies-Tibber-Bridge/0.0.1"
ICON_POWER = 26337 # Drawing power
ICON_SOLAR = 54077 # Feeding power

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def get_tibber_config():
    """
    Phase 1: HTTP Bootstrap.
    Fetch both the WebSocket URL and homes with real-time meter.
    """
    if not TIBBER_TOKEN:
        logger.error("TIBBER_TOKEN not found.")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {TIBBER_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT
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
        response = requests.post(TIBBER_ENDPOINT, json={"query": query}, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"HTTP Bootstrap failed: {e}")
        sys.exit(1)

    viewer = data.get('data', {}).get('viewer', {})
    wss_url = viewer.get('websocketSubscriptionUrl')
    homes = viewer.get('homes', [])

    # Find the first home with an active Pulse
    active_home_id = None
    for home in homes:
        if home.get('features', {}).get('realTimeConsumptionEnabled'):
            active_home_id = home['id']
            logger.info(f"Found home: {home.get('appNickname') or 'Home'} ({active_home_id})")
            break
    
    if not wss_url:
        logger.error("Tibber API: No WebSocket URL received.")
        sys.exit(1)
    
    if not active_home_id:
        logger.error("Tibber API: No home with Pulse found (realTimeConsumptionEnabled=True).")
        sys.exit(1)

    return wss_url, active_home_id


def send_http_payload(payload):
    """
    Executes the HTTP Push to LaMetric Time.
    Is ran in a thread to not block the main loop.
    """
    if not LAMETRIC_URL or not LAMETRIC_API_KEY:
        logger.warning("LaMetric configuration missing (LAMETRIC_URL or LAMETRIC_API_KEY). Skipping push.")
        return

    try:
        r = requests.post(
            LAMETRIC_URL,
            json=payload,
            auth=("dev", LAMETRIC_API_KEY),
            timeout=2
        )
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"LaMetric: Failed HTTP POST {e}")


async def push_to_lametric(power):
    """
    Formats the data and sends it to a thread.
    """
    # Are we importing power, or exporting it?
    if power < 0:
        icon = ICON_SOLAR
    else:
        icon = ICON_POWER

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
    await asyncio.to_thread(send_http_payload, payload)

async def tibber_stream(wss_url, home_id):
    """
    Phase 2: WebSocket Stream (graphql-transport-ws protocol).
    """
    sub_query = f"""
    subscription {{
      liveMeasurement(homeId: "{home_id}") {{
        timestamp
        power
      }}
    }}
    """

    # Protocol headers
    # Note: Tibber requires 'graphql-transport-ws' subprotocol.
    # Also add Token to the connection payload (see init_msg).
    
    logger.info(f"Tibber API: Connect WebSocket {wss_url}")
    
    async for websocket in websockets.connect(
        wss_url,
        subprotocols=["graphql-transport-ws"],
        additional_headers={"User-Agent": USER_AGENT}
    ):
        try:
            # --- STEP A: Connection Init ---
            # We are required to introduce ourselves.
            init_msg = {
                "type": "connection_init",
                "payload": {"token": TIBBER_TOKEN}
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

                    # --- PUSH TO LAMETRIC TIME ---
                    if power is not None:
                        await push_to_lametric(power)
                    
                    # --- OUTPUT TO STDOUT ---
                    logger.info(f"Tibber API: [{timestamp}] Power: {power} W")
                
                elif msg_type == "error":
                    logger.error(f"Tibber API: Stream error: {data}")
                
                elif msg_type == "complete":
                    logger.info("Tibber API: Server stopped the stream.")
                    break

        except websockets.ConnectionClosed as e:
            logger.warning(f"Tibber API: Connection closed: {e}. Restarting in 5s...")
            continue
        except Exception as e:
            logger.error(f"Tibber API: Unexpected error: {e}")
            await asyncio.sleep(5)

async def main():
    # 1. Fetch config
    wss_url, home_id = get_tibber_config()
    
    # 2. Start async loop with auto-reconnect logic
    while True:
        try:
            await tibber_stream(wss_url, home_id)
        except Exception as e:
            logger.error(f"Main loop crash: {e}")
        
        logger.info("Sleeping before reconnect...")
        await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script stopped by user.")

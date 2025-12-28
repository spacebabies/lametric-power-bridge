import argparse
import asyncio
import logging
import os
import sys
import time

from dotenv import load_dotenv

# Load configuration from single .env file
load_dotenv("lametric-power-bridge.env")

from sources.tibber import TibberSource
from sources.homewizard_p1 import HomeWizardP1Source
from sinks.lametric import push_to_lametric, push_to_lametric_stale

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Stale data timeout (seconds)
STALE_DATA_TIMEOUT = 60

def get_source(source_name: str):
    """Initialize the selected power source with hard fail on misconfiguration"""
    if source_name == "tibber":
        token = os.getenv("TIBBER_TOKEN")
        if not token:
            logger.error("Tibber: TIBBER_TOKEN not configured in lametric-power-bridge.env")
            sys.exit(1)
        logger.info(f"Using source: Tibber")
        return TibberSource(token=token)
    elif source_name == "homewizard-p1":
        host = os.getenv("HOMEWIZARD_P1_HOST")
        if not host:
            logger.error("HomeWizard P1: HOMEWIZARD_P1_HOST not configured in lametric-power-bridge.env")
            sys.exit(1)
        logger.info(f"Using source: HomeWizard P1 (v1 API)")
        return HomeWizardP1Source(host=host)
    else:
        logger.error(f"Unknown source: {source_name}")
        sys.exit(1)

async def main(source_name: str):
    # Initialize selected source
    source = get_source(source_name)

    # Connect (HTTP bootstrap)
    await source.connect()

    # Shared state for timeout monitoring
    state = {
        "last_reading_time": time.time(),
        "stale_alert_sent": False
    }

    async def timeout_monitor():
        """Monitor that checks if data has gone stale"""
        while True:
            await asyncio.sleep(10)  # Check every 10 seconds

            time_since_last_reading = time.time() - state["last_reading_time"]

            if time_since_last_reading > STALE_DATA_TIMEOUT:
                if not state["stale_alert_sent"]:
                    logger.warning(f"No data received for {STALE_DATA_TIMEOUT}s, pushing stale indicator")
                    await push_to_lametric_stale()
                    state["stale_alert_sent"] = True
            else:
                # Reset stale flag when data is fresh
                state["stale_alert_sent"] = False

    async def stream_readings():
        """Stream power readings with auto-reconnect"""
        while True:
            try:
                async for reading in source.stream():
                    # Update timestamp
                    state["last_reading_time"] = time.time()

                    # Push to LaMetric
                    await push_to_lametric(reading)

                    # Log to stdout
                    logger.info(f"[{reading.timestamp}] Power: {reading.power_watts} W")
            except Exception as e:
                logger.error(f"Stream error: {e}")
                await asyncio.sleep(5)

    # Run stream and timeout monitor in parallel
    async with asyncio.TaskGroup() as tg:
        tg.create_task(stream_readings())
        tg.create_task(timeout_monitor())

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="LaMetric Power Bridge")
    parser.add_argument(
        "--source",
        type=str,
        default="tibber",
        choices=["tibber", "homewizard-p1"],
        help="Power source to use (default: tibber)"
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.source))
    except KeyboardInterrupt:
        logger.info("Script stopped by user.")

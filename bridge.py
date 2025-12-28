import asyncio
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv("tibber.env")

from sources.tibber import TibberSource
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

async def main():
    # Initialize Tibber source
    source = TibberSource(token=os.environ.get("TIBBER_TOKEN"))

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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script stopped by user.")

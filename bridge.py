import asyncio
import logging
import os

from dotenv import load_dotenv
from sources.tibber import TibberSource
from sinks.lametric import push_to_lametric

load_dotenv("tibber.env")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

async def main():
    # Initialize Tibber source
    source = TibberSource(token=os.environ.get("TIBBER_TOKEN"))

    # Connect (HTTP bootstrap)
    await source.connect()

    # Stream power readings with auto-reconnect
    while True:
        try:
            async for reading in source.stream():
                # Push to LaMetric
                await push_to_lametric(reading)

                # Log to stdout
                logger.info(f"[{reading.timestamp}] Power: {reading.power_watts} W")
        except Exception as e:
            logger.error(f"Stream error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script stopped by user.")

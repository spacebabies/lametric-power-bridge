"""LaMetric Time egress module - formats and pushes power data via HTTP"""
import asyncio
import logging
import os
import requests

from sources.base import PowerReading

logger = logging.getLogger(__name__)

# Configuration
LAMETRIC_API_KEY = os.environ.get("LAMETRIC_API_KEY")
LAMETRIC_URL = os.environ.get("LAMETRIC_URL")
ICON_POWER = 26337  # Drawing power
ICON_SOLAR = 54077  # Feeding power
ICON_STALE = 1059   # Lightning bolt with red slash (no data)


def _perform_http_request(payload):
    """
    Executes the HTTP Push to LaMetric Time.
    Is ran in a thread to not block the main loop.
    """
    if not LAMETRIC_URL or not LAMETRIC_API_KEY:
        logger.warning("LaMetric configuration missing. Skipping push.")
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


async def send_http_payload(payload):
    """
    Offloads the blocking HTTP request to a thread.
    """
    await asyncio.to_thread(_perform_http_request, payload)


async def push_to_lametric(reading: PowerReading):
    """
    Formats the data and sends it to a thread.

    Args:
        reading: PowerReading object with power measurement
    """
    power = round(reading.power_watts)

    # Are we importing power, or exporting it?
    if power < 0:
        icon = ICON_SOLAR
    else:
        icon = ICON_POWER

    # If power is more than 10000 W, show in kW with one decimal
    if abs(power) >= 10000:
        power_kw = power / 1000
        text = f"{power_kw:.1f} kW"
    else:
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
    await send_http_payload(payload)


async def push_to_lametric_stale():
    """
    Pushes a stale data indicator to LaMetric when no data is received.
    Shows "-- W" with a lightning bolt with red slash icon.
    """
    payload = {
        "frames": [
            {
                "text": "-- W",
                "icon": ICON_STALE,
                "index": 0
            }
        ]
    }

    await send_http_payload(payload)

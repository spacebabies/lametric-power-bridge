# LaMetric Power Bridge ⚡️

A robust, real-time bridge to push live energy consumption data to **LaMetric Time**.

Designed to run as a background service on a local server (Debian/Raspberry Pi), this tool connects to energy providers (currently **Tibber**, with **P1/HomeWizard** support coming soon) and pushes live wattage updates directly to your LaMetric device via the local network.

It is built to be "fail-safe": it handles network dropouts, API reconnects, and device unavailability gracefully without crashing.

## Features

* **Real-time:** Updates as fast as the source allows (e.g., ~2s for Tibber Pulse).
* **Local Push:** Uses LaMetric's Local API (no cloud delay for the display update).
* **Visual Feedback:** Dynamically changes icons for consumption (⚡️) vs. solar return (☀️).
* **Robust:** Auto-reconnect strategies for WebSockets and non-blocking HTTP pushes.
* **Daemon-ready:** Includes systemd configuration for 24/7 operation.

## Architecture

The application is designed with a pluggable architecture in mind:

1.  **Ingress (Source):** Connects to data provider (Currently: Tibber via GraphQL/WSS).
2.  **Logic:** Normalizes data (positive/negative handling).
3.  **Egress (Sink):** Pushes formatted frames to LaMetric.

## Installation

### Prerequisites

* Python 3.9+
* A LaMetric Time device (Developer Mode enabled)
* A Tibber Pulse (for the Tibber backend)

### 1. Clone & Setup

```bash
git clone [https://github.com/yourusername/lametric-power-bridge.git](https://github.com/yourusername/lametric-power-bridge.git)
cd lametric-power-bridge

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

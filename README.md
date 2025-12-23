# LaMetric Power Bridge ⚡️

A robust, real-time bridge to push live power data to **LaMetric Time**.

![Photo of a LaMetric Time with "⚡️ 3517 W" on its display](https://github.com/user-attachments/assets/38b71bdb-2986-449c-b10c-d7640edbeb6d)

Designed to run as a background service on a local server (Debian/Raspberry Pi), this tool connects to realtime power measurements (currently **Tibber Pulse**, with P1 Serial, and HomeWizard support coming soon) and pushes live wattage updates directly to your LaMetric device via the local network.

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
* A "smart" or connected electricity meter, ostensibly
* A Tibber Pulse (for the Tibber backend)

### 0. LaMetric Time Configuration

1. Open the LaMetric Time mobile app and select your device.
2. Click the `+` sign (Market)
3. Add **My Data DIY**, published by LaMetric
4. Give it a name and choose **HTTP Push** as the Type.
5. Note the Push URL, this goes into `LAMETRIC_URL` configuration value.

<img width="216" height="480" alt="Screenshot of My Data DIY LaMetric Time app configuration" src="https://github.com/user-attachments/assets/25f1e4f3-ad1a-48f8-a646-132e96c5a7ab" />

### 1. Clone & Setup

```bash
git clone https://github.com/spacebabies/lametric-power-bridge.git
cd lametric-power-bridge

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration

Copy the included `.env` file to store your secrets.

```bash
cp tibber.env.example tibber.env
nano tibber.env
```

### 3. Run manually

```bash
python bridge.py
```

## Running as a Service (Systemd)

To ensure the bridge runs 24/7 and restarts on failure, install it as a systemd service.

1. Edit the provided `tibber-bridge.service` to match your paths and user.
2. Copy to systemd:
    ```bash
    sudo cp lametric-power-bridge.service /etc/systemd/system/
    ```
3. Enable and start:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable --now lametric-power-bridge
    ```
4. Check logs:
    ```bash
    sudo journalctl -u lametric-power-bridge -f
    ```

## Roadmap

- [x] Tibber Pulse Backend (GraphQL WSS)
- [ ] DSMR P1 Cable Backend (Serial/USB)
- [ ] HomeWizard Wi-Fi P1 Backend
- [ ] Multi-frame support (e.g. Gas usage, Voltage per phase)

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**. You are free to use, modify, and distribute this software, but any modifications distributed must remain open-source under the same license. Commercial closed-source use is prohibited.

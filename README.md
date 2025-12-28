# LaMetric Power Bridge ⚡️

A mildly adequate solution for obsessively watching your money burn in real-time.

![Photo of a LaMetric Time with "⚡️ 3517 W" on its display](https://github.com/user-attachments/assets/38b71bdb-2986-449c-b10c-d7640edbeb6d)

Designed to run as a background service on a local server (Debian/Raspberry Pi), this tool connects to realtime power measurements from various sources (**Tibber Pulse** via WebSocket, or **HomeWizard P1 Meter** via HTTP polling, with P1 Serial support coming when I can be bothered) and pushes live wattage updates directly to your LaMetric device via the local network.

I built this because routing your living room's energy data through a server in Virginia just to display a number three feet away seemed a bit excessive.

## Features

* **Real-time-ish:** Updates as fast as the source allows. If Tibber is lagging, we lag. We are a bridge, not a time machine.
* **Local Push:** Uses LaMetric's Local API. We prefer our packets free-range and organic.
* **Visual Feedback:** Displays a yellow lightning bolt (⚡️) when you are paying, and a green one (EMOJI_INEXPLICABLY_MISSING_FROM_UNICODE) when nature is paying you. Simple shapes for complex financial anxiety.
* **Robust:** "Fail-safe." This is a technical term meaning "it crashes with dignity and restarts before you notice."
* **Daemon-ready:** Includes systemd configuration, because running scripts in a `screen` session is for amateurs.

## Architecture

The application utilizes a bespoke, highly sophisticated "pluggable architecture." In layman's terms, it is a Python script in three trench coats:

1.  **Ingress (Source):** Reluctantly accepts data from the provider (Tibber via GraphQL/WSS, or HomeWizard P1 via HTTP GET, because variety is the spice of unnecessary complexity).
2.  **Logic:** Performs complex mathematical wizardry (it checks if the number is negative).
3.  **Egress (Sink):** Shouts the result at the LaMetric device until it complies.

## Installation

### Prerequisites

*   **Python 3.9+** (It is almost 2026; please keep up).
*   **A LaMetric Time device** (An expensive pixel clock that has no business costing this much).
*   **A "smart" electricity meter** (A digital spy kindly forced upon you by the grid operator to "modernize" your ability to be monitored).
*   **One of the following data sources:**
    *   **Tibber Pulse** (Because if your data is going to be harvested by a third party, you should at least have the dignity to pay €50 for the privilege).
    *   **HomeWizard P1 Meter** (A tiny box that sits between your smart meter and your Wi-Fi router, politely asking for permission to read numbers once per second. Refreshingly local, which is the entire point).

### 0. LaMetric Time Configuration

1.  Open the LaMetric Time mobile app and select your device.
2.  Click the `+` sign (Market).
3.  Add **My Data DIY**, published by LaMetric.
4.  Give it a name and choose **HTTP Push**.
5.  Note the **Push URL**. You will need this later. Do not lose it.

<img width="216" height="480" alt="Screenshot of My Data DIY LaMetric Time app configuration" src="https://github.com/user-attachments/assets/25f1e4f3-ad1a-48f8-a646-132e96c5a7ab" />

### 1. Clone & Setup

```bash
git clone git@github.com:spacebabies/lametric-power-bridge.git
cd lametric-power-bridge

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration

Choose your poison.

#### 2a. Tibber Configuration

Copy the included `.env` file. I have provided an example, which I trust is sufficient for someone of your caliber.

```bash
cp tibber.env.example tibber.env
vim tibber.env  # Do not let me catch you using nano.
```

#### 2b. HomeWizard P1 Configuration

For those who prefer their data without a middleman. Admirable, if slightly paranoid.

```bash
cp homewizard-p1.env.example homewizard-p1.env
vim homewizard-p1.env  # The same warning about nano applies.
```

You will need the local IP address of your HomeWizard P1 Meter. This can typically be found in your router's DHCP table, or by asking the HomeWizard Energy app politely.

### 3. Run manually

If you must.

```bash
# Tibber (default)
python bridge.py

# HomeWizard P1 Meter
python bridge.py --source=homewizard-p1
```

The bridge defaults to Tibber for backwards compatibility. If you configured HomeWizard, you must explicitly specify `--source=homewizard-p1`. This is intentional. I am not your butler.

## Running as a Service (systemd)

To ensure the bridge runs 24/7 and restarts when the inevitable entropy of the universe takes hold:

1. Edit the provided `lametric-power-bridge.service` to match your paths and user.
   - If using HomeWizard, add `--source=homewizard-p1` to the `ExecStart` line. The service file defaults to Tibber, naturally.
2. Copy to systemd:
    ```bash
    sudo cp lametric-power-bridge.service /etc/systemd/system/
    ```
3. Enable and start:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable --now lametric-power-bridge
    ```
4. Check logs (to see exactly what went wrong):
    ```bash
    sudo journalctl -u lametric-power-bridge -f
    ```

## Roadmap

- [x] Tibber Pulse Backend (GraphQL WSS)
- [x] HomeWizard P1 Meter Backend (v1 HTTP Polling API) — _For those who trust Wi-Fi but distrust cloud services_
- [ ] HomeWizard P1 Meter Backend (v2 WebSocket API) — _Same device, slightly fancier protocol_
- [ ] DSMR P1 Cable Backend (For those who prefer wires and have USB ports to spare)
- [ ] Multi-frame support (e.g., Gas usage, or perhaps the current price of tea)

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**.

You are free to use, modify, and distribute this software. However, if you represent a multinational energy conglomerate or a smart-home startup looking to package this into a monthly subscription service: **Go away**.

_Commercial closed-source use is prohibited, and quite frankly, against the spirit of everything decent._

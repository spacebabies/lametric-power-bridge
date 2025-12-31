# LaMetric Power Bridge ⚡️

A mildly adequate solution for obsessively watching your money burn in real-time.

![Photo of a LaMetric Time with "⚡️ 3517 W" on its display](https://github.com/user-attachments/assets/38b71bdb-2986-449c-b10c-d7640edbeb6d)

Designed to run as a background service on a local server (Debian/Raspberry Pi), this tool connects to realtime power measurements from various sources (**Tibber Pulse** via WebSocket, or **HomeWizard Energy** devices via HTTP/WebSocket, with P1 Serial support coming when I can be bothered) and pushes live wattage updates directly to your LaMetric device via the local network.

I built this because routing your living room's energy data through a server in Virginia just to display a number three feet away seemed a bit excessive.

## Features

* **Real-time-ish:** Updates as fast as the source allows. If Tibber is lagging, we lag. We are a bridge, not a time machine.
* **Local Push:** Uses LaMetric's Local API. We prefer our packets free-range and organic.
* **Visual Feedback:** Displays a yellow lightning bolt (⚡️) when you are paying, and a green one (EMOJI_INEXPLICABLY_MISSING_FROM_UNICODE) when nature is paying you. Simple shapes for complex financial anxiety.
* **Robust:** "Fail-safe." This is a technical term meaning "it crashes with dignity and restarts before you notice."
* **Daemon-ready:** Includes systemd configuration, because running scripts in a `screen` session is for amateurs.

## Architecture

The application utilizes a bespoke, highly sophisticated "pluggable architecture." In layman's terms, it is a Python script in three trench coats:

1.  **Ingress (Source):** Reluctantly accepts data from the provider (Tibber via GraphQL/WSS, or HomeWizard via HTTP/WebSocket, because variety is the spice of unnecessary complexity).
2.  **Logic:** Performs complex mathematical wizardry (it checks if the number is negative).
3.  **Egress (Sink):** Shouts the result at the LaMetric device until it complies.

## Installation

### Prerequisites

*   **Python 3.9+** (It is almost 2026; please keep up).
*   **A LaMetric Time device** (An expensive pixel clock that has no business costing this much).
*   **A "smart" electricity meter** (A digital spy kindly forced upon you by the grid operator to "modernize" your ability to be monitored).
*   **One of the following data sources:**
    *   **Tibber Pulse** (Because if your data is going to be harvested by a third party, you should at least have the dignity to pay €50 for the privilege).
    *   **HomeWizard Energy** device (A tiny box that sits between your smart meter and your Wi-Fi router, politely asking for permission to read numbers once per second. Refreshingly local, which is the entire point).

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

Copy the provided `.env` example file and configure your data source(s). I have provided extensive comments within, which I trust are sufficient for someone of your caliber.

```bash
cp lametric-power-bridge.env.example lametric-power-bridge.env
vim lametric-power-bridge.env  # Do not let me catch you using nano.
```

**Required for all sources:**
- `LAMETRIC_URL`: Your LaMetric Push URL (from the My Data DIY app)
- `LAMETRIC_API_KEY`: Your LaMetric API key

**Source-specific configuration:**
- **Tibber:** Set `TIBBER_TOKEN` (from developer.tibber.com)
- **HomeWizard v1:** Set `HOMEWIZARD_HOST` (local IP address of your device)
- **HomeWizard v2:** Set `HOMEWIZARD_HOST` and `HOMEWIZARD_TOKEN` (requires firmware >= 6.0 and manual token creation)

You will need the local IP address of your HomeWizard device if using that source. This can typically be found in your router's DHCP table, or by asking the HomeWizard Energy app politely.

### 3. Run manually

If you must.

```bash
# Tibber (default)
python bridge.py

# HomeWizard v1 API (HTTP polling)
python bridge.py --source=homewizard-v1

# HomeWizard v2 API (WebSocket)
python bridge.py --source=homewizard-v2
```

The bridge defaults to Tibber for backwards compatibility. If you configured HomeWizard, you must explicitly specify which API version to use. This is intentional. I am not your butler.

### HomeWizard API Versions: A Brief Exercise in Patience

HomeWizard, in their infinite wisdom, has blessed us with **two distinct API versions** for essentially the same task. Allow me to illuminate the differences:

#### v1 API (HTTP Polling) - `--source=homewizard-v1`
- **Transport:** HTTP GET requests, sent every second, like a needy houseguest checking if dinner is ready.
- **Availability:** Works on **all** HomeWizard Energy devices, including those running firmware from the Paleolithic era.
- **Performance:** Adequate. Your device will not complain. Much.
- **Use this if:** You value compatibility over the marginal thrill of push-based updates, or your device firmware predates the invention of WebSockets.

#### v2 API (WebSocket) - `--source=homewizard-v2`
- **Transport:** WebSocket. The device _pushes_ updates to you, unprompted, like a modern miracle.
- **Availability:** Requires **firmware >= 6.0**. Check yours with: `curl http://YOUR_IP/api` and inspect the `firmware_version` field. If it says something like "2.47", you are stuck in the past.
- **Authentication:** Requires creating a local user account via the API. This is a _delightful_ multi-step ceremony involving HTTP POST requests and token management. See below for the ritual.
- **Performance:** Technically superior. Fewer HTTP round-trips. More efficient. Objectively better. Push-based updates instead of polling.
- **Use this if:** Your firmware is up to date, you appreciate technological progress, and you are prepared to execute the token creation ritual without complaint.

##### Creating a Local User Token (v2 API Only)

The v2 API requires authentication via a local user token. This token is _not_ your Wi-Fi password, nor is it available in any app. You must conjure it yourself using the device's REST API.

**Step 1:** Create a new local user (replace `YOUR_IP` with your device IP):

```bash
curl -X POST http://YOUR_IP/api/v1/user \
  -H "Content-Type: application/json" \
  -d '{"name": "lametric-bridge", "password": "your_secure_password_here"}'
```

**Step 2:** The device will respond with a JSON object containing your `token`. Copy this token and paste it into your `lametric-power-bridge.env` file as `HOMEWIZARD_TOKEN`.

**Step 3:** Never lose this token. The device will not remind you what it was, and you will have to create a new user if you forget it.

If this process feels unnecessarily convoluted, you are correct. Use v1 instead and save yourself the trouble.

**In summary:**
v1 works everywhere but involves polling (sad). v2 is better but requires firmware >= 6.0 and a token creation ritual (tedious). Choose based on your tolerance for obsolescence versus bureaucracy.

## Running as a Service (systemd)

To ensure the bridge runs 24/7 and restarts when the inevitable entropy of the universe takes hold:

1. Edit the provided `lametric-power-bridge.service` to match your paths and user.
   - If using HomeWizard, add `--source=homewizard-v1` to the `ExecStart` line. The service file defaults to Tibber, naturally.
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
- [x] HomeWizard v1 API Backend (HTTP Polling) — _For those who trust Wi-Fi but distrust cloud services_
- [x] HomeWizard v2 API Backend (WebSocket) — _Same device, slightly fancier protocol, requires recent firmware and a token ritual_
- [ ] DSMR P1 Cable Backend (For those who prefer wires and have USB ports to spare)
- [ ] Multi-frame support (e.g., Gas usage, or perhaps the current price of tea)

## Acknowledgments

Built with the **[HomeWizard Energy](https://www.homewizard.com/)** local API. Special thanks to the HomeWizard team for providing a well-documented local API that respects user privacy and enables creative integrations like this one.

**Developer Note**: Implementation patterns inspired by HomeWizard's excellent **[python-homewizard-energy](https://github.com/homewizard/python-homewizard-energy)** library, particularly the async context manager pattern and API versioning approach. If you're building HomeWizard integrations in Python, I highly recommend checking out their official library.

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**.

You are free to use, modify, and distribute this software. However, if you represent a multinational energy conglomerate or a smart-home startup looking to package this into a monthly subscription service: **Go away**.

_Commercial closed-source use is prohibited, and quite frankly, against the spirit of everything decent._

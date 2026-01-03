# LaMetric Power Bridge ⚡️

A mildly adequate solution for obsessively watching your money burn in real-time.

![Photo of a LaMetric Time with "⚡️ 3517 W" on its display](https://github.com/user-attachments/assets/38b71bdb-2986-449c-b10c-d7640edbeb6d)

Designed to run as a background service on a local server (Debian/Raspberry Pi), this tool connects to realtime power measurements from various sources (Tibber Pulse via WebSocket, or [HomeWizard P1 Meter](https://www.homewizard.com/p1-meter/) via HTTP/WebSocket, or P1 Serial cable for maximum hax0r creds) and pushes live wattage updates directly to your LaMetric device via the local network.

I built this because routing your living room's energy data through a server in Virginia just to display a number three feet away seemed a bit excessive.

## Features

* **Real-time-ish:** Updates as fast as the source allows. If they lag, we lag. We are a bridge, not a time machine.
* **Local Push:** Uses LaMetric's Local API. We prefer our packets free-range and organic.
* **Visual Feedback:** Displays a yellow lightning bolt (⚡️) when you are paying, and a green one (EMOJI_INEXPLICABLY_MISSING_FROM_UNICODE) when nature is paying you. Simple shapes for complex financial anxiety.
* **Robust:** "Fail-safe." This is a technical term meaning "it crashes with dignity and restarts before you notice."
* **Daemon-ready:** Includes systemd configuration, because running scripts in a `screen` session is for amateurs.

## Architecture

The application utilizes a bespoke, highly sophisticated "pluggable architecture." In layman's terms, it is a Python script in three trench coats:

1.  **Ingress (Source):** Reluctantly accepts data from a choice of providers (because variety is the spice of unnecessary complexity).
2.  **Logic:** Performs complex mathematical wizardry (it checks if the number is negative).
3.  **Egress (Sink):** Shouts the result at the LaMetric device until it complies.

## Installation

### Prerequisites

*   **Python 3.9+** (It is 2026; please keep up).
*   **A LaMetric Time device** (An expensive pixel clock that has no business costing this much).
*   **A "smart" electricity meter** (A digital spy kindly forced upon you by the grid operator to "modernize" your ability to be monitored).
*   **One of the following data sources:**
    *   **Tibber Pulse** (Because if your data is going to be harvested by a third party, you should at least have the dignity to pay €50 for the privilege).
    *   **HomeWizard P1 Meter** (A tiny box that sits between your smart meter and your Wi-Fi router, politely asking for permission to read numbers once per second. Refreshingly local, which is the entire point).
    *   **P1 Serial Cable** (A USB-to-RJ11 adapter that plugs directly into your smart meter's P1 port. No cloud, no Wi-Fi, just pure unfiltered DSMR telegrams over a serial connection. The most dignified option, assuming you can locate a free USB port on your server and possess the necessary permissions to access `/dev/ttyUSB0` without incident).

### 0. LaMetric Time Configuration

1.  Open the LaMetric Time mobile app and select your device.
2.  Click the `+` sign (Market).
3.  Add **My Data DIY**, published by LaMetric.
4.  Give it a name and choose **HTTP Push**.
5.  Grab the **API Key** from the [developer portal](https://developer.lametric.com/user/devices). (2022 models or later also show this in the app)

The bridge will discover your LaMetric Time device on your local network automatically via SSDP. This works if you have exactly one device. If you have multiple devices or discovery fails, you can manually configure the Push URL in the `.env` file.

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
- `LAMETRIC_API_KEY`: We cannot work with your display without its special code.

**Optional (auto-discovery recommended):**
- `LAMETRIC_URL`: Your LaMetric Push URL - Leave empty to use auto-discovery. Only configure this manually if you have multiple LaMetric devices or auto-discovery fails.

**Source-specific configuration:**
- **Tibber:** Set `TIBBER_TOKEN` (from developer.tibber.com)
- **HomeWizard v1:** `HOMEWIZARD_HOST` is optional (auto-discovery used if empty)
- **HomeWizard v2:** Set `HOMEWIZARD_TOKEN` (required) and optionally `HOMEWIZARD_HOST`
- **P1 Serial:** Optionally set `P1_SERIAL_DEVICE` (defaults to `/dev/ttyUSB0`) and `P1_SERIAL_BAUDRATE` (defaults to `115200` for DSMR v4+, use `9600` if your meter predates the invention of high-speed serial communication)

You will need the local IP address of your HomeWizard device ONLY if auto-discovery fails or you have multiple devices. Otherwise, enjoy the magic of mDNS.

**About auto-discovery:**
The bridge supports auto-discovery for both LaMetric and HomeWizard devices:
- **LaMetric:** Discovered via SSDP (Simple Service Discovery Protocol). If exactly one device is found, it updates your push URL automatically.
- **HomeWizard:** Discovered via mDNS (Multicast DNS). If `HOMEWIZARD_HOST` is left empty, the bridge will find your "HWE-P1" meter automatically.

This ensures that even if your router decides to assign new IP addresses (DHCP renewal), the bridge will re-discover the devices and continue functioning without intervention.

### 3. Run manually

If you must.

```bash
# Tibber (default)
python bridge.py

# HomeWizard v1 API (HTTP polling)
python bridge.py --source=homewizard-v1

# HomeWizard v2 API (WebSocket)
python bridge.py --source=homewizard-v2

# P1 Serial (direct cable, no intermediaries)
python bridge.py --source=p1-serial
```

The bridge defaults to Tibber for backwards compatibility. If you configured HomeWizard or P1 Serial, you must explicitly specify your chosen source. This is intentional. I am not your butler.

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

The v2 API requires [authentication](https://api-documentation.homewizard.com/docs/v2/authorization) via a local user token. This token is _not_ your Wi-Fi password, nor is it available in any app. You must conjure it yourself using the device's REST API.

**Step 1:** Create a new local user (replace `YOUR_IP` with your device IP):

```bash
curl http://YOUR_IP/api/user \
  --insecure \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-Api-Version: 2" \
  -d '{"name": "local/lametric-power-bridge"}'
```

The API will respond with an error. This is fine.

**Step 2:** Press the physical button on the device and repeat the exact same request. And do it with zest, because this is a time-sensitive dance.

**Step 3:** The device will now respond with a JSON object containing your `token`. Copy this token and paste it into your `lametric-power-bridge.env` file as `HOMEWIZARD_TOKEN`.

Never lose this token. The device will not remind you what it was, and you will have to create a new user if you forget it.

If this process feels unnecessarily convoluted, you are correct. Use v1 instead and save yourself the trouble.

**In summary:**
v1 works everywhere but involves polling (sad). v2 is better but requires firmware >= 6.0 and a token creation ritual (tedious). Choose based on your tolerance for obsolescence versus bureaucracy.

### P1 Serial: For The Purists

If you prefer your data _unmediated_ by cloud services, Wi-Fi chipsets, or indeed any third-party hardware whatsoever, you may connect directly to the smart meter's P1 port using a USB-to-serial cable.

**Requirements:**
- A **P1 cable** (USB-to-RJ11, widely available for €10-30, or DIY if you enjoy soldering).
- **DSMR v4+ meter** (115200 baud) or **DSMR v2/v3** (9600 baud, if your meter is vintage).

**How it works:**
The meter broadcasts DSMR telegrams every second over the P1 port. This implementation:
- Reads raw telegrams via `pyserial`
- Validates CRC16 checksums (polynomial 0xA001, for the pedants)
- Parses OBIS codes `1-0:1.7.0` (consumption) and `1-0:2.7.0` (production)
- Yields `PowerReading` objects to the bridge

No HTTP requests. No GraphQL subscriptions. No WebSocket handshakes. Just bytes over a wire, as nature intended.

**Debugging:**
If the cable is not detected, verify it exists:
```bash
ls -la /dev/ttyUSB*
```
If nothing appears, check that the cable is actually plugged in. It happens to the best of us.

## Running as a Service (systemd)

To ensure the bridge runs 24/7 and restarts when the inevitable entropy of the universe takes hold:

1. Edit the provided `lametric-power-bridge.service` to match your paths and user.
   - Configure your choice of input by adding `--source=<SOURCE>` to the `ExecStart` line.
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
- [x] DSMR P1 Serial Backend — _For those who prefer wires, possess USB ports, and appreciate the purity of electrons over copper_
- [ ] Multi-frame support (e.g., Gas usage, or perhaps the current price of tea)

## Acknowledgments

Built with the **[HomeWizard Energy](https://www.homewizard.com/)** local API. Special thanks to the HomeWizard team for providing a well-documented local API that respects user privacy and enables creative integrations like this one.

**Developer Note**: Implementation patterns inspired by HomeWizard's excellent **[python-homewizard-energy](https://github.com/homewizard/python-homewizard-energy)** library, particularly the async context manager pattern and API versioning approach. If you're building HomeWizard integrations in Python, I highly recommend checking out their official library.

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**.

You are free to use, modify, and distribute this software. However, if you represent a multinational energy conglomerate or a smart-home startup looking to package this into a monthly subscription service: **Go away**.

_Commercial closed-source use is prohibited, and quite frankly, against the spirit of everything decent._

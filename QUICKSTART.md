# PaperHub Quickstart Guide

> **Ambient E-Ink Touch Controller for Home Assistant**  
> *Transform consumer e-readers into zero-latency, multi-week battery smart home touch remotes.*

> [!NOTE]
> ⚡ **Disclaimer — Vibe-Coded Project Notice**:  
> PaperHub is proudly **vibe-coded** from the ground up. It was conceived, architected, refined, and built through prompt-driven agentic pairing to solve a real itch: consumer E-Ink readers (Onyx Boox, Kindle, Kobo, reMarkable) have gorgeous displays and weeks of battery life, but running Home Assistant Lovelace on them is an unbearable, battery-draining slog. Expect rapid iteration, opinionated Apple craftsmanship, and clean code crafted with obsessive attention to detail.

---

## 💡 How It Actually Works (The ELI5 Explanation)

If you've ever tried loading Home Assistant on a Kindle or Onyx Boox, you know why it feels unusable: standard Home Assistant dashboards are heavy web apps with thousands of lines of HTML, CSS, JavaScript, and animations. An e-reader's tiny battery-saving processor chokes trying to parse all that, lagging 2 full seconds per tap and dying in an afternoon.

**PaperHub solves this by doing all the hard work on your server:**

1. **The Server Draws the Pictures**: Your Home Assistant machine (Raspberry Pi, NUC, Mini PC) has plenty of horsepower. PaperHub rasterizes your dashboard into a crisp, pixel-perfect 16-level grayscale image in **~15 milliseconds**.
2. **Your E-Reader Is Just a Smart Picture Frame**: Your device doesn't run any heavy code. It literally just displays that single image fullscreen.
3. **Taps Send Raw Coordinates `(X, Y)`**: When you tap your finger on the screen (e.g. on a "Living Room Light" button), your device doesn't run complex JavaScript. It just tells Home Assistant: *"Hey, the user tapped at X=420, Y=350."*
4. **Instant Action & Instant Update**: Home Assistant looks up what's at that position, toggles your light, redraws the picture with the light shown as ON, and sends the updated picture back to the device in under 50 milliseconds.
5. **E-Book Page Flipping ("Book Metaphor")**: Just like reading a book on your Kindle or Boox:
   - Tap anywhere on the **left 15% edge** of the screen $\to$ Go to previous page.
   - Tap anywhere on the **right 15% edge** of the screen $\to$ Go to next page.
   - Or swipe horizontally left / right with your finger.

Because the e-reader's processor does virtually zero computation, it never overheats, never lags, and the battery lasts **weeks instead of hours**.

---

## 1. Install PaperHub in Home Assistant

### Requirements
- Home Assistant OS or Home Assistant Supervised (with Add-on store support).
- Your Home Assistant's local IP address (e.g. `192.168.1.50`).

### Installation Steps
1. In Home Assistant, navigate to **Settings → Add-ons → Add-on Store**.
2. Click the three dots menu (top-right corner) → **Repositories**.
3. Paste the PaperHub repository URL and click **Add**:
   ```text
   https://github.com/bek00letz/paperhub
   ```
4. Find **PaperHub** in the repository list and click **Install** (takes ~1 minute).
5. On the add-on page, enable:
   - **Start on boot**
   - **Watchdog**
   - **Show in sidebar**
6. Click **Start**. You will now see **PaperHub** with an e-paper tablet icon in your Home Assistant left sidebar.

---

## 2. Customize Your Dashboard in the Visual Editor

1. Click **PaperHub** in your Home Assistant sidebar.
2. In the top toolbar, select your device from the **Model** dropdown:
   - **Onyx Boox Go 6** (1072 × 1448, 300 PPI)
   - **Kindle Paperwhite 11th Gen** (1264 × 1680, 300 PPI)
   - **Kobo Clara / Libra** (300 PPI)
   - **Kindle Scribe / Note Air** (10.3″ Large Format)
   - **TRMNL OG / TRMNL X** (800 × 480 / 1872 × 1404)
3. Click **＋ Preset** to add ready-made screens:
   - **Agenda**: Features a chronological Calendar Timeline and 5-Day Weather Forecast.
   - **Ambient Home**: A 4-spot or 6-spot Dynamic Grid for primary room lights and switches.
   - **Climate & Comfort**: Thermostat sliders, temperature history sparklines, and HVAC controls.
4. Click on any card or icon to inspect its properties:
   - Under **Touch & Remote Interaction**, pick your action (`Toggle Entity`, `Turn On`, `Call Service`, or `Jump to Page`).
5. **Test it immediately without your device**:
   - Click the **Simulate Touch** button in the toolbar.
   - Click anywhere on the canvas to see simulated tactile ripple animations and toast feedback confirming that Home Assistant services would trigger.
6. Click **Push to Devices** to save your layout.

---

## 3. Connect Your Device to PaperHub

Different devices run different software. Choose the section below matching your hardware:

### Option A: Onyx Boox & Android E-Readers (Boox Go 6, Page, Palma, Meebook)

Because Onyx Boox runs Android with full Google Chrome and capacitive touch, this is the easiest and most polished setup:

1. **Connect to Wi-Fi**: Make sure your Boox is connected to the same home Wi-Fi network as Home Assistant.
2. **Open the Browser**: On your Boox, open **Chrome** (or **NeoBrowser** / **Fully Kiosk Browser**).
3. **Type the PaperHub Kiosk URL**:
   ```text
   http://<YOUR_HA_IP>:8099/kiosk/boox
   ```
   *(Replace `<YOUR_HA_IP>` with your Home Assistant IP, e.g. `http://192.168.1.50:8099/kiosk/boox`).*
4. **Make it Fullscreen (PWA Mode)**:
   - In Chrome, tap the top-right three dots menu `⋮` $\to$ tap **Add to Home screen** (or **Install app**).
   - An icon called **PaperHub** will appear on your Boox home screen. Tap it to launch PaperHub in true borderless, zero-distraction fullscreen!
5. **Optimize Onyx E-Ink Center Settings** (Crucial for best experience):
   - Swipe down from the top-right of your Boox screen to open the **Control Center / E-Ink Center**.
   - **Refresh Mode**: Set to **Regal Mode** (gives crisp, razor-sharp text with zero flashing).
   - **Animation Filter Delay**: Drag slider to `0` (instant reaction).
   - **Full Refresh Frequency**: Set to 30 or 50 operations.
6. **Enjoy!** Tap any light card to toggle it instantly, or tap the screen edges to flip pages.

---

### Option B: Jailbroken Kindle (Paperwhite, Oasis, Voyage, Scribe)

Jailbroken Kindles don't need a web browser at all. They run a tiny Linux daemon that writes images straight to the screen framebuffer (`/dev/fb0`) and listens to touch interrupts (`/dev/input/event0`):

1. Connect to your jailbroken Kindle via SSH or launch a terminal via KUAL.
2. Download or copy `client/linux/paperhub-daemon.sh` to `/mnt/us/paperhub/`.
3. Launch the background daemon:
   ```bash
   chmod +x /mnt/us/paperhub/paperhub-daemon.sh
   PAPERHUB_SERVER="http://<YOUR_HA_IP>:8099" PAPERHUB_DEVICE="kindle_pw" /mnt/us/paperhub/paperhub-daemon.sh &
   ```
4. The daemon fetches the frame, caches the ETag, and goes to sleep. When you tap the screen, the Linux kernel wakes up the script in 1ms, posts your tap coordinates to PaperHub, and updates the display!

---

### Option C: Kobo E-Readers (Clara, Libra, Forma, Elipsa)

1. Launch a shell on your Kobo via **NickelMenu** or SSH.
2. Stop the default Nickel e-reading software:
   ```bash
   killall -TERM nickel
   ```
3. Run the PaperHub client daemon:
   ```bash
   chmod +x paperhub-daemon.sh
   PAPERHUB_SERVER="http://<YOUR_HA_IP>:8099" PAPERHUB_DEVICE="kobo_clara" ./paperhub-daemon.sh &
   ```

---

### Option D: TRMNL E-Ink Display (ESP32 / BYOS)

TRMNL devices use Wi-Fi sleep and wake up every few minutes to pull an image:

1. Open your TRMNL dashboard or device configuration.
2. Set the custom **BYOS (Bring Your Own Server)** webhook URL to:
   ```text
   http://<YOUR_HA_IP>:8099/api/trmnl
   ```
3. PaperHub will automatically generate uncompressed 1-bit monochrome BMP images (`/frame.bmp`), read your battery voltage, and keep your TRMNL up to date with zero RAM decompression overhead on the ESP32!

---

### Option E: Any Tablet, iPad, Phone, or Computer

You don't even need an e-reader to try PaperHub! Any device with a modern browser can load the kiosk:

1. On your iPad, iPhone, Android tablet, or laptop browser, visit:
   ```text
   http://<YOUR_HA_IP>:8099/kiosk/tablet
   ```
2. You get an ultra-clean, Apple-styled ambient touch dashboard that updates in real time via Server-Sent Events.

---

## 4. Navigation & Gesture Cheatsheet

| Gesture | Where to Tap / Swipe | What It Does |
|---|---|---|
| **Turn Page Back** | Tap within the **left 15%** of the screen | Flips to the previous dashboard page |
| **Turn Page Forward** | Tap within the **right 15%** of the screen | Flips to the next dashboard page |
| **Swipe Left** | Swipe right-to-left across the screen | Advances to next page |
| **Swipe Right** | Swipe left-to-right across the screen | Returns to previous page |
| **Element Tap** | Tap any button, card, or dynamic grid icon | Instantly toggles entity or runs service in Home Assistant |

---

## 5. Frequently Asked Questions & Troubleshooting

### Why port `8099` instead of `8080`?
- **Port 8080** is the **Editor & Admin Port**. It runs inside Home Assistant's secure Ingress tunnel with full authentication.
- **Port 8099** is the **LAN E-Reader Port**. It is specifically opened on your local network so low-power e-readers and microcontrollers can fetch pictures and send tap coordinates without needing complex OAuth2 logins, cookie management, or 2-factor authentication.

### How do I find my Home Assistant IP address (`<YOUR_HA_IP>`)?
In Home Assistant, go to **Settings → System → Network**. Look under **Home Assistant URL** or **Network Adapter** for your local IPv4 address (e.g. `192.168.1.150` or `homeassistant.local`).

### My Boox screen flashes black on every tap. How do I fix it?
Swipe down from the top-right corner to open the Onyx **E-Ink Center**. Change your app refresh mode to **Regal Mode** or **Speed / A2 Mode**. In Regal mode, Carta e-ink displays perform partial updates without full screen inverted flashes.

### Does PaperHub drain my e-reader's battery?
No! Because the browser only renders a static `<img>` and has no background animations, your e-reader's processor stays idle 99.9% of the time. On a Boox Go 6 with Wi-Fi on, you can expect **weeks of battery life** instead of hours.

---

## License
MIT License. Crafted with obsessive care and vibe-coded polish.

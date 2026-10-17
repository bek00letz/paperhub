# PaperHub Quickstart Guide

Get your e-reader running as an ambient Home Assistant touch remote in under 5 minutes.

---

## 1. Install PaperHub Add-on in Home Assistant

1. In Home Assistant, navigate to **Settings → Add-ons → Add-on Store**.
2. Click the three dots (top-right) → **Repositories** → Add:
   ```text
   https://github.com/bek00letz/paperhub
   ```
3. Locate **PaperHub** in the store list and click **Install**.
4. Enable **Start on boot** and **Watchdog**, then click **Start**.
5. Click **Open Web UI** or access **PaperHub** directly in your Home Assistant sidebar.

---

## 2. Design Your Screens in the Visual Editor

1. Open PaperHub from the sidebar.
2. Select your device model in the top toolbar:
   - **Onyx Boox Go 6** (1072 × 1448, 300 PPI)
   - **Kindle Paperwhite (11th Gen)** (1264 × 1680, 300 PPI)
   - **Kobo Clara / Libra** (300 PPI)
   - **Kindle Scribe / Note Air** (10.3″ Large Format)
3. Click **＋ Preset** to load ready-to-use screens (`Ambient Home`, `Climate Control`, `Scenes & Remote`).
4. Click on any card or button to inspect its properties:
   - Under **Touch & Remote Interaction**, choose the action: `Toggle Entity`, `Turn On`, `Jump to Page`, or `Call Service`.
5. Click **Push to Devices** to render and deploy.

---

## 3. Connect Your E-Reader Device

### Option A: Onyx Boox / Android E-Readers (Recommended)

1. Open **Chrome** or **Fully Kiosk Browser** on your Boox Go 6.
2. Navigate to:
   ```text
   http://<YOUR_HA_IP>:8099/kiosk/boox_livingroom
   ```
3. In browser settings, add to Home Screen to run fullscreen as a standalone PWA.
4. Set E-Ink refresh mode to **Regal Mode** in the Onyx E-Ink Center for crisp, flash-free partial updates.

---

### Option B: Jailbroken Kindle (Paperwhite, Oasis, Scribe)

1. Connect to your jailbroken Kindle via SSH or KUAL.
2. Download and run the PaperHub Linux daemon:
   ```bash
   PAPERHUB_SERVER="http://<YOUR_HA_IP>:8099" PAPERHUB_DEVICE="kindle_pw" /mnt/us/paperhub/paperhub-daemon.sh
   ```
3. Your Kindle will render the 16-level grayscale screen and listen for touch taps via `/dev/input/event0`.

---

### Option C: Kobo E-Readers (Clara, Libra, Forma)

1. Launch a terminal shell on your Kobo (via NickelMenu or SSH).
2. Stop the stock Nickel reader UI:
   ```bash
   killall -TERM nickel
   ```
3. Run the daemon:
   ```bash
   PAPERHUB_SERVER="http://<YOUR_HA_IP>:8099" PAPERHUB_DEVICE="kobo_clara" ./paperhub-daemon.sh &
   ```

---

## 4. Navigation & Gestures

- **Page Flipping ("Book Metaphor")**:
  - Tap anywhere within the **left 15%** of the screen to go to the **Previous Page**.
  - Tap anywhere within the **right 15%** of the screen to go to the **Next Page**.
- **Remote Swiping**:
  - Swipe left horizontally to flip to the next page.
  - Swipe right horizontally to return to the previous page.
- **Center Taps**:
  - Tapping a button, card, or dynamic grid spot triggers the configured entity toggle or service instantly in Home Assistant.

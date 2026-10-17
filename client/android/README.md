# PaperHub for Android E-Readers (Onyx Boox, Meebook, Bigme)

This guide covers running PaperHub on modern Android-powered e-readers such as:
- **Onyx Boox Go 6 (6.0″ Carta 1300, 300 PPI)**
- **Onyx Boox Page & Leaf 2 (7.0″ Carta 1200, 300 PPI)**
- **Onyx Boox Note Air 3 / Palma / Tab Series**
- **Meebook M6, M7, P78 Pro**
- **Bigme B751 / S6**

---

## Deployment Strategy 1: Universal Kiosk PWA (Recommended)

PaperHub's Kiosk PWA is zero-DOM and renders only a single `<img>` tag that captures touch coordinates and gestures.

### Recommended Browser: Fully Kiosk Browser or Chrome

1. **Install Fully Kiosk Browser** (available via Google Play or sideload from fully-kiosk.com).
2. **Set Start URL:**
   ```text
   http://<YOUR_HA_IP>:8099/kiosk/boox_bedroom
   ```
3. **Configure E-Ink Optimization in Fully Kiosk:**
   - **Web Zoom and Scaling:** Enable *Auto-fit to Screen*.
   - **Keep Screen On / Wake Lock:** Enabled (if used as ambient dock) or set *Turn Screen Off after 5 min* (for remote usage).
   - **Disable Pull to Refresh:** Prevents accidental browser gesture interference with PaperHub page navigation.
   - **Hardware Acceleration:** Set to *Disabled* (E-ink software rasterization behaves better without GPU composition overhead).

---

## E-Ink Refresh Mode Optimization (Onyx Boox)

On Onyx Boox devices, open the **E-Ink Center** (swipe down from top-right corner):
1. **Refresh Mode:** Select **Regal Mode** or **Normal Mode**.
   - *Regal Mode* clears ghosting on partial updates without black/white flashing inversion.
   - Do NOT use *Speed Mode* or *X-Mode* for PaperHub, as 16-level grayscale typography looks noticeably softer in high-speed dithered modes.
2. **Full Refresh Frequency:** Set to **After 30 or 50 taps**.
3. **Animation Filter:** Set delay to **0ms** (PaperHub animations are instant server-side renders).
4. **DPI Scaling:** Leave at native **300 DPI** (or standard 100% scale).

---

## Frontlight & Night Mode Sync

To control the Onyx Boox dual-color frontlight (warm amber and cold white LEDs) from Home Assistant:
1. Install the official **Home Assistant Android Companion App** on your Boox.
2. The companion app creates brightness and sensor entities in Home Assistant.
3. Use Home Assistant automations to sync room lighting with your e-reader frontlight:
   - When room lights turn off, dim the Boox warm frontlight to 2%.
   - During daytime, turn frontlights completely off for 100% ambient reflective Carta paper reading.

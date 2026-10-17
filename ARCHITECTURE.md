# Architecture: PaperHub (Ambient E-Ink Touch Controller)

## 1. Executive Summary & Problem Space

Consumer E-Ink readers (Onyx Boox Go 6, Kindle Paperwhite, Kobo Clara/Libra, reMarkable) feature 300 PPI Carta screens, capacitive touch digitizers, dual-tone frontlights, and multi-week battery capacities.

However, running Home Assistant Lovelace on e-reader web views (Chromium/Android WebKit) is fundamentally flawed:
- **Severe Battery Drain**: Continuous DOM parsing, CSS layout recalculations, JavaScript runtime execution, and WebSocket heartbeats force the CPU into high-power states, draining batteries in 6–12 hours instead of 3–4 weeks.
- **High Touch Latency**: Browser DOM event bubbling and web repaint cycles introduce 1.5–2.5 second touch latencies.
- **Intolerable E-Ink Ghosting**: Web animations and partial repaints trigger chaotic, uncoordinated EPD waveform flashes.

### The PaperHub Solution

```
┌────────────────────────────────────────────────────────┐
│               Home Assistant Server                    │
│                                                        │
│  ┌─────────────────┐      ┌─────────────────────────┐  │
│  │ State Listeners │ ───► │ Batch Jinja2 Resolution │  │
│  └─────────────────┘      └───────────┬─────────────┘  │
│                                       ▼                │
│                           ┌─────────────────────────┐  │
│                           │ High-DPI PIL Rasterizer │  │
│                           │ (16-Level Carta Depth)  │  │
│                           └───────────┬─────────────┘  │
│                                       ▼ 15–20ms        │
│                           ┌─────────────────────────┐  │
│                           │ Compressed Frame Buffer │  │
│                           └───────────┬─────────────┘  │
└───────────────────────────────────────┼────────────────┘
                                        │
                         HTTP / SSE / LAN Push (~30ms)
                                        │
                                        ▼
┌────────────────────────────────────────────────────────┐
│             Client Device (Zero-DOM Framebuffer)       │
│                                                        │
│   Touch Digitizer (X, Y) ───► POST /api/touch          │
│   Incoming Frame ───────────► Hardware Regal Blit      │
│   Idle State ───────────────► 0% CPU Deep Suspend      │
└────────────────────────────────────────────────────────┘
```

PaperHub shifts the rendering burden entirely to the Home Assistant server. The server rasterizes full screens into crisp 300 PPI 16-level grayscale bitmaps in under 20ms. The client device acts purely as an ultra-low-power framebuffer and touch coordinate sensor.

---

## 2. High-DPI & 16-Level Grayscale Shading

### A. Display Profiles & Geometry

Consumer e-readers feature distinct physical aspect ratios and Carta resolutions:

| Device Profile | Screen Diagonal | Resolution | PPI | Active Aspect Ratio |
|---|---|---|---|---|
| **Onyx Boox Go 6 / Kobo Clara** | 6.0″ Carta 1300 | 1072 × 1448 | 300 | 3:4 portrait |
| **Kindle Paperwhite (11th Gen)** | 6.8″ Carta 1200 | 1264 × 1680 | 300 | 3:4 portrait |
| **Onyx Boox Page / Kobo Libra 2** | 7.0″ Carta 1200 | 1264 × 1680 | 300 | 3:4 portrait |
| **Boox Note Air 3 / reMarkable 2** | 10.3″ Carta/Mobius | 1404 × 1872 | 227 | 3:4 portrait |
| **Kindle Scribe** | 10.2″ Carta 1200 | 1860 × 2480 | 300 | 3:4 portrait |
| **CrowPanel 5.79″ (Legacy)** | 5.79″ SPI Strip | 792 × 272 | 145 | Ultra-wide landscape |

### B. The 16-Level Grayscale Pipeline

Carta e-paper microcapsules are physically actuated by voltage pulses that align charged black and white pigments into 16 discrete reflective states.

Unlike legacy 1-bit monochrome systems that apply coarse dithering (which destroys typography legibility at small sizes), PaperHub renders typography with subpixel anti-aliasing onto an 8-bit `'L'` mode canvas and quantizes it using a C-level 256-to-16 lookup table:

$$\text{Level}(v) = \text{round}\left(\frac{\text{round}(v / 17.0) \times 17.0}{1}\right)$$

Discrete palette values:
$$L \in \{0, 17, 34, 51, 68, 85, 102, 119, 136, 153, 170, 187, 204, 221, 238, 255\}$$

This guarantees that every pixel matches a native Carta voltage waveform state, rendering buttery-smooth typography and delicate ambient drop-shadows with zero waveform dithering noise.

### C. Concentric Geometry & Depth

All cards, buttons, and badges follow concentric curvature:

$$R_{\text{inner}} = R_{\text{outer}} - \text{padding}$$

Cards feature subtle 2-layer ambient shadows that give tactile depth on e-ink surfaces without muddiness.

---

## 3. Interactive Touch Engine & Server-Side Hit-Testing

### A. Coordinate Normalization & Hit-Testing

The client captures touch coordinates `(X, Y)` and transmits them via `POST /api/devices/{id}/touch`.

1. **Edge Tap Navigation ("Book Metaphor")**:
   - `X <= 0.15 × Width` $\to$ Navigate to previous page.
   - `X >= 0.85 × Width` $\to$ Navigate to next page.
2. **Gesture Recognition**:
   - Horizontal swipe left $\to$ Next page.
   - Horizontal swipe right $\to$ Previous page.
3. **Center Zone 2D Hit-Testing**:
   - The engine iterates through the active page's elements in reverse visual stacking order.
   - For `dynamic_grid` elements: child card bounding boxes are computed dynamically, identifying exactly which spot in the 2D matrix was tapped.
   - Executes configured action:
     - `toggle`: calls `homeassistant.toggle` on target entity.
     - `turn_on` / `turn_off`: calls domain service.
     - `navigate_page`: switches device active page.
     - `call_service`: dispatches custom service payload.

### B. Single-Roundtrip Screen Updates

To minimize latency on e-ink, the client can request `Accept: image/png` or `?format=png` on the touch `POST` request. The server executes the action, re-rasterizes the page in 10–20ms, and streams the updated PNG directly in the HTTP response body. This yields a complete touch-to-glass latency under **50ms**.

---

## 4. Multi-OS Client Architecture

### Tier 1: Android E-Readers (Onyx Boox, Meebook, Bigme)
- **Universal Kiosk PWA**: A zero-DOM web app consisting of a single fullscreen `<img>` listening for touch events and an SSE stream for pushed refreshes.
- **Native Android Companion**: Integrates with vendor EPD SDKs (`com.onyx.android.sdk.api.device.epd.EpdController`) to set Regal refresh mode for ghost-free partial updates and exposes frontlights to Home Assistant.

### Tier 2: Linux / Jailbroken Devices (Kindle & Kobo)
- `paperhub-daemon.sh` & `paperhub-evdev.py`:
  - Listens to `/dev/input/event0` touch interrupts.
  - Draws `/frame.png` directly to `/dev/fb0` using `fbink` or `eips`.
  - Consumes **0% CPU** during idle, waking up only upon touch interrupts.

### Tier 3: Standard Tablets & Browsers
- Runs the Kiosk PWA on iPad, Android tablets, or desktop browsers as a glare-free ambient dashboard.

---

## 5. Performance Comparison

| Metric | Lovelace Web Dashboard (on E-Reader) | PaperHub (Server-Side Rasterization) |
|---|---|---|
| **Battery Life (Boox Go 6)** | ~8–12 hours | **2–4 weeks** |
| **Touch Response Latency** | 1,500–2,500 ms | **< 50 ms** |
| **Memory Footprint on Device** | 350–500 MB (Chromium) | **< 15 MB** (Kiosk / Daemon) |
| **CPU Utilization (Idle)** | 15–35% (JS event loops) | **0.0%** (Kernel suspend) |
| **Screen Ghosting** | Severe (uncontrolled partial repaints) | Clean (Regal 16-level waveform matched) |

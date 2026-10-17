# Changelog

## 1.2.0 - Apple Home Control Tiles, Smart Drag-and-Drop, and Live Touch Simulation

- **First-Class Apple Home Control Tiles (`tile`)**:
  - Replaced primitive text-only states with high-DPI squircle cards adhering to the Apple Craftsmanship Standard ($R_{\text{outer}} = 22\text{--}24\text{px}$, circular icon well $R_{\text{inner}} = 22\text{px}$).
  - True 16-level Carta grayscale anti-aliasing with delicate hairline borders and ambient soft drop-shadows.
  - Full state-aware dynamic styling:
    - **ON**: Inverted solid black circular well with crisp white MDI glyph, bold primary title, dynamic status subtitle (`On • 80%`), and active accent pill indicator.
    - **OFF**: Crisp off-white card surface, outline circular well with muted dark-gray glyph, and secondary `Off` label.
    - Supports both **Standard** (light card + inverted well) and **Inverted** (deep solid black card) aesthetic styles.
  - Built-in domain specialized variants: `light_tile`, `switch_tile`, `climate_tile`, `sensor_tile`, `action_tile`.
  - Automatic $\ge 44\text{pt}$ touch targets for comfortable physical tapping on capacitive e-reader screens.
- **Smart Drag-and-Drop & Entity Explorer**:
  - Dragging or adding entities onto the canvas now automatically provisions fully configured Apple Home Tiles.
  - Intelligent domain heuristics: auto-suggests primary titles from friendly names, pairs active and off outline icons (e.g. `mdi:lightbulb` $\to$ `mdi:lightbulb-outline`), and sets appropriate touch actions (`toggle` for lights/switches, `turn_on` for scenes/scripts, `none` for sensors).
  - Dragging calendar entities automatically provisions the Calendar Timeline widget; dragging weather entities provisions the 5-day Weather Forecast widget.
- **Live In-Memory Touch Simulation (Zero Coordinate Drift)**:
  - Fixed touch simulation disconnect where the simulator was hit-testing stale disk layouts.
  - The editor now transmits live in-memory screen structures (`page: page()`) directly to `POST /api/touch`, enabling instant testing of newly added or moved elements before saving to disk.
  - Tapping in simulation mode directly triggers live Home Assistant service calls (`homeassistant.toggle`) and re-renders the canvas preview in ~20ms.
- **Visual Editor Inspector & Quick-Add Palette**:
  - Added dedicated Tile Configuration inspector with live fields for Title, Entity, Subtitle (with custom Jinja template support), Active Icon, Off Icon, Card Style, Radius, and Top-Right Badge.
  - Integrated visual MDI icon picker buttons directly into the tile inspector for active and off glyphs.
  - Added quick-add palette buttons for Light Tile, Switch Tile, Climate, Sensor, and Action.
- **Ambient Home Screen Preset Redesign**:
  - Completely refreshed default `"home"` layout in `default_layouts.json`:
    - Large typographic room header and date.
    - Balanced 2-column grid of 6 Apple Control Tiles: Ceiling Light, Reading Lamp, Ceiling Fan, Thermostat, Sonos Speaker, and Evening Relax Scene.
    - 5-Day Weather Outlook and Calendar Schedule Timeline widgets.
    - Subtle edge-tap pagination guide.
  - Full 1072 × 1448 frame rasterization completes in **34ms**.
- **Automated Test Suite**:
  - Added unit tests for Apple Home tile rasterization (standard and inverted styles), automatic tile hit-testing, and live-page touch simulation. All 11 tests passing.

## 1.1.0 - TRMNL Support, Calendar & Weather Widgets, Conditional ETag Caching

- **TRMNL Hardware & Zero-RAM Direct BMP Streaming**:
  - Added native display profiles for `trmnl_og` (800 × 480, 120 PPI) and `trmnl_x` (1872 × 1404, 227 PPI).
  - Added 1-bit monochrome uncompressed BMP output (`/frame.bmp` and `/api/devices/{device_id}/frame.bmp`, 48,062 bytes for 800x480). Streams directly into ESP32 display controllers with zero microcontroller RAM overhead.
  - Added TRMNL BYOS-compatible webhook endpoint (`/api/trmnl`) parsing hardware MAC and battery voltage headers to track device battery health.
- **Conditional ETag HTTP 304 Caching**:
  - Implemented HTTP `ETag` and `If-None-Match` handling across all frame endpoints (`/frame.png`, `/frame.bmp`).
  - Unchanged screens return HTTP 304 without response body, saving 98%+ Wi-Fi network traffic and preventing unnecessary e-ink flashing.
  - Updated Linux daemons (`paperhub-daemon.sh` and `paperhub-evdev.py`) to poll with ETag caching.
- **Rich Calendar & Weather Widgets (Apple Craftsmanship Standard)**:
  - Added `calendar_timeline` widget: Chronological schedule view with concentric card container, event nodes, and active "NOW • HH:MM" pill indicator.
  - Added `weather_forecast` widget: 5-day forecast columns with MDI weather icons, temperature hi/lo ranges, and precipitation probability badges (`💧 40%`).
  - Added pre-configured "Agenda" screen preset to `default_layouts.json`.
- **Multilingual Typography Fallback**:
  - Automatic glyph inspection selecting `DejaVuSans` for non-Latin characters and symbols (Cyrillic, Greek, math, arrows `→`, stars `★`, and degree symbols `℃`), preventing empty box glyphs (`□`).
- **Interactive Simulator in Visual Editor**:
  - Added `Simulate Touch` mode to test edge-turn zone navigation, capacitive button taps, and entity actions directly on the editor canvas with animated ripple feedback.
  - Added one-click widget presets for Calendar Timeline and Weather Forecast in the component palette and template library.
- **Automated Verification Suite**:
  - Added automated unit and async endpoint test suite in `addon/app/tests/test_paperhub.py`.

## 1.0.0 - Project Inception

- **High-DPI Consumer E-Reader Profiles**:
  - Onyx Boox Go 6 (1072 × 1448, 300 PPI Carta 1300)
  - Kindle Paperwhite 11th Gen (1264 × 1680, 300 PPI)
  - Kobo Clara 2E / BW (1072 × 1448, 300 PPI)
  - Onyx Boox Page & Kobo Libra 2 (1264 × 1680, 300 PPI)
  - Onyx Boox Note Air 3 & reMarkable 2 (1404 × 1872, 227 PPI)
  - Kindle Scribe 10.2" (1860 × 2480, 300 PPI)
  - CrowPanel 5.79" (792 × 272 legacy)
- **16-Level Grayscale Rendering**: True 4-bit Carta native palette with anti-aliased FreeType typography, concentric geometry ($R_{inner} = R_{outer} - padding$), and ambient multi-layer drop-shadows.
- **Server-Side Interactive Touch Engine**:
  - Sub-20ms 2D hit-testing for capacitive touch buttons, dynamic grids, and cards.
  - "Book Metaphor" edge navigation zones (15% left -> prev page, 15% right -> next page).
  - Horizontal swipe gesture detection (swipe left -> next page, swipe right -> prev page).
  - Direct single-roundtrip touch update (`format=png`) for instantaneous screen refresh.
- **Multi-Device Session Management**:
  - Dedicated state tracking per device ID (`active_page`, `orientation`, `edge_nav`, `battery_pct`).
  - Real-time Server-Sent Events (SSE) push stream for instant refresh on entity state changes.
- **Cross-Platform Client Strategy**:
  - Universal Kiosk PWA (zero-DOM, fullscreen, touch & swipe enabled).
  - Linux/Jailbreak daemon for Kindle and Kobo (`fbink` / `eips` + `/dev/input/event0`).
  - Native Android companion specification for Onyx Boox EPD SDK (Regal partial refresh & frontlight sync).
- **WYSIWYG Visual Editor**:
  - Device Profile Selector with live canvas dimension switching.
  - Interactive Touch & Remote Interaction inspector.
  - Toggleable 15% Edge Turn Zone guides.
  - Tactile touch target indicators (`👆`) on interactive elements.

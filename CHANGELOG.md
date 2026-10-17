# Changelog

## 1.5.0 - Airspace Radar, Flight Telemetry, Formula 1 Pit-Wall & Live Sports Scoreboards

- **Overhead Airspace Radar & Flight Telemetry (`flight_tracker` / `flight_radar`)**:
  - **Tactical 360° Circular PPI Radar Scope**: Concentric range rings, cardinal heading labels (N, E, S, W), range scale indicators, and directional aircraft chevrons rotated to real-time `track_deg` heading, with a targeted corner reticle around the closest or selected aircraft.
  - **Full Commercial Telemetry Card**: High-contrast metrics card displaying callsign, airline/country, altitude with dynamic climb/descent arrow (`↑`, `↓`, `→`), ground speed, heading, and ADS-B squawk/ICAO.
  - **Orientation-Adaptive Split Layout**:
    - **Landscape / Wide cards ($w \ge 1.15 \times h$)**: Radar scope on the left ($\sim 40\%$ width) with telemetry card on the right.
    - **Portrait / Tall cards ($h > w$)**: Radar scope on the top ($\sim 48\%$ height) with telemetry card on the bottom, perfectly adapted for portrait readers like Onyx Boox Go 6 (1072 × 1448).
  - **Live Geodesic ADS-B Tracking**: Queries the OpenSky Network API relative to the Home Assistant `zone.home` coordinates with configurable radius, distance sorting, and caching.
- **Formula 1 & Motorsport Live Pit-Wall (`sports_racing`)**:
  - **Live Leaderboard**: Real-time Top 10 driver standings with position badges (`P1`), driver codes (`VER`, `NOR`), team names, gap intervals (`LEADER`, `+2.1s`), tyre compound badges (`[S]`, `[M]`, `[H]`, `[I]`, `[W]`), and lap count (`LAP 42/53`).
  - **Responsive Column Architecture**: 2-column leaderboard for cards with $w \ge 520\text{px}$; 1-column leaderboard for narrow cards.
  - **Off-Week & Pre-Race Session Countdown**: Clean ambient view showing circuit name, location, and upcoming Grand Prix session date/time.
  - **Data Sources**: Integrates with ESPN F1 scoreboard API and Home Assistant `sensor.f1`.
- **Live Multi-League Sports Scoreboards (`sports_match`)**:
  - **Head-to-Head Hero Presentation**: Bold score display (`2 — 1`), home and away team names, match stats (shots, possession, records, down & distance), and period clock/status badge (`74' · 2ND HALF`, `FINAL`).
  - **Match Highlights & Scorers**: Chronological goal scorers and key play ticker at the base of the card.
  - **Multi-League Support**: Built-in support for Premier League (EPL), UEFA Champions League, La Liga, Bundesliga, Serie A, MLS, NBA Basketball, NFL Football, MLB Baseball, NHL Hockey, and Home Assistant `ha-teamtracker` sensors.
- **Visual Editor & Template Presets**:
  - Added dedicated quick-add toolbar buttons for Radar (`✈️`), F1 Racing (`🏎️`), and Match (`⚽`).
  - Added full inspector property controls for style selection, radar radius, racing series, league pickers, and entity overrides.
  - Added 4 rich template cards to the Preset Library: *Airspace Radar Scope*, *Flight Tracker & Telemetry*, *Formula 1 Pit-Wall*, and *Live Sports Scoreboard*.
- **Automated Test Suite**:
  - Added 5 new automated tests verifying radar scope, portrait split adaptation, F1 pit-wall, live match scoreboards, and seamless offline data enrichment (27 total tests, 100% passing in <0.3s).

## 1.4.0 - Ultra-Low-Power Architecture, Power & Sync Profiles, and Smart Selective Push

- **Adaptive Power & Sync Architecture**:
  - **User Choice for Device Role**: Fully configurable screen operating mode per device:
    - **Interactive Touch Dashboard**: Responsive touch controls for toggling lights, calling scenes, and flipping pages with instant touch wake.
    - **View-Only Ambient Frame**: Pure presentation canvas (wall art, family calendar). Taps navigate pages or wake the screen, while completely suppressing accidental entity toggles and Home Assistant state mutations.
  - **Unconstrained Background Refresh Interval**:
    - Open numeric input supporting any interval from 0 to 10,080 minutes (7 days), paired with quick preset chips (`0m / Touch Only`, `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `12h`, `24h`).
    - Setting 0 puts the tablet into deep sleep: zero periodic radio/CPU wakeups, refreshing strictly on physical touch or server push.
  - **Smart Selective Push on Active Screen Entity Change**:
    - Even with devices set to long intervals (e.g. 5 hours) to conserve battery, PaperHub inspects layout elements, dynamic grids, and template expressions. When an entity visible on the device's *currently active screen* updates in Home Assistant, the server immediately pushes a redraw over WebSocket/SSE. Off-screen entity updates never wake the tablet.
  - **Configurable Night Hibernation & Quiet Hours**:
    - Configurable time range (defaults to 23:00 to 07:00).
    - Configurable night interval ($0 = \text{deep sleep until morning}$).
    - Optional Home Assistant entity trigger (e.g. `input_boolean.sleep_mode`): when active, the device enters hibernation immediately regardless of the clock, saving ~8 hours of active battery every night.
  - **Standard Frontlight Best Practice**:
    - Establishes frontlight off (0%) by default, saving 3x–5x battery life on reflective e-ink Carta displays without complex lux sensors.
- **Dedicated Power & Sync Profile UI**:
  - Replaced the legacy fixed slider with `#powersyncbtn` in the stage toolbar and a dedicated menu item in the Settings popover.
  - Beautiful Apple-standard modal (`#powersyncwrap`) with concentric cards, fluid transitions, tactile preset chips, and live battery impact hints.
  - Per-device profile management via `GET /api/devices/{device_id}` and `POST /api/devices/{device_id}`.
- **Client Runtime & Firmware Headers**:
  - Injected `X-PaperHub-Next-Wake`, `X-PaperHub-Refresh-Interval`, `X-PaperHub-Screen-Mode`, and standard HTTP `Refresh` headers into `/frame.png` and `/frame.bmp` (including HTTP 304 Not Modified).
  - TRMNL webhook endpoint automatically computes adaptive sleep duration based on active quiet hours and power profile.
  - Updated Kiosk and PWA client runtimes to sync device power config on boot and visibility change, eliminating unneeded background polling.
- **Automated Test Suite**:
  - Added 6 new unit tests covering power profile calculation, quiet hours with HA triggers, selective page entity filtering, view-only suppression, and header injection (22 total tests, 100% passing).

## 1.3.0 - Intelligent Edge Zones, Custom Canvases, Live WebSocket Updates & Modern Responsive Reflow

- **Intelligent Edge Turn Zones ("Book Metaphor" Navigation)**:
  - **Single Page Auto-Suppression**: When a dashboard has only 1 screen/page, edge turn zones are automatically disabled and hidden, liberating the full 100% canvas width for widgets and tiles.
  - **Multi-Page Safe Canvas Constraints**: When 2 or more pages exist, configurable 15% edge zones become active and physically constrain the canvas. Element dragging, resizing, arrow-key nudging, duplication, and alignment buttons (`Center X`, `Full Width`) strictly respect the `[edgeZoneW, curW - edgeZoneW]` safe boundaries, preventing cards from overlapping gutters.
  - **Visual Chevrons**: Active edge zones display large, elegant single-arrow chevrons (`‹` and `›`, SF Pro Display 42px) with clean labels both in the visual editor and on rendered e-reader frames.
  - **Swipe-Only Toggle**: Users can disable edge zones via toolbar toggle (`📖 Edge Zones`) to rely purely on swipe gestures (`swipe_left` / `swipe_right`) across multi-page setups.
  - **Element Touch Priority**: Server-side hit-testing prioritizes interactive elements first. Tapping an element near the margin always triggers the entity action; page turns occur only if a tap lands in an empty gutter.
- **Real-Time Live Updates without Manual Refresh**:
  - **Home Assistant WebSocket Event Stream**: Background listener connects directly to HA core WebSocket (`http://supervisor/core/websocket`), authenticates via `SUPERVISOR_TOKEN`, and subscribes to `state_changed` events.
  - **Instant Push Invalidation**: Whenever any entity changes (e.g. temperature sensor updates from 21.4°C to 21.5°C, or a light switch toggles), PaperHub invalidates caches and immediately pushes real-time Server-Sent Events (SSE) to connected tablets, Chrome kiosks, and PWA clients.
  - **Fallback Periodic Refresh**: Added 30-second background poll in Kiosk and PWA frontends plus server ticker loop, guaranteeing clocks, calendars, and sensors stay fresh even if Wi-Fi or SSE blips.
- **Custom Canvas Dimensions**:
  - Added arbitrary custom canvas sizing (`spec.display = "custom"`) with inline Width, Height, and PPI inputs in the editor toolbar.
  - Full server-side rasterization and hit-testing support for non-standard e-ink displays, custom HDMI/EPD monitors, and DIY projects.
- **Dynamic State-Aware Icons (E-Ink High Contrast)**:
  - Implemented comprehensive `DYNAMIC_ICON_PAIRS` dictionary and smart heuristic fallbacks for lights, switches, fans, climate, doors, windows, locks, media players, and security sensors (e.g. `mdi:lightbulb` $\leftrightarrow$ `mdi:lightbulb-outline`, `mdi:fan` $\leftrightarrow$ `mdi:fan-off`, `mdi:door-open` $\leftrightarrow$ `mdi:door-closed`, `mdi:volume-high` $\leftrightarrow$ `mdi:volume-off`).
  - Automatically swaps icon glyphs on inactive states while preserving typography contrast on grayscale Carta screens.
- **Friendly Name Normalization**:
  - Fixed entity resolution so `attributes.friendly_name` is cleanly mapped to `name` across REST `/states`, fixture data, and frontend datalists, eliminating raw entity ID fallbacks.
- **Modern Responsive Reflow**:
  - Replaced legacy hardcoded 272×792 shelf tag reflow with modern multi-column responsive layout engine (3-4 columns for high-DPI landscape, 2 columns for portrait, full width for widgets).
- **Expanded Test Suite**:
  - Added 5 new automated tests in `test_paperhub.py` (16 total, 100% passing).

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

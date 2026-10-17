# Changelog

## 1.5.4 - True Responsive Reflow Engine, Zero Tile Overlap & Toolbar Reflow Action

- **True Responsive Reflow Engine**:
  - Completely replaced naive ratio coordinate scaling with a structural, grid-aware responsive reflow engine.
  - Automatically groups tiles and buttons into visual rows based on vertical proximity and calculates exact, non-overlapping column widths with uniform gaps ($\text{tileW} = \lfloor (usableW - (N - 1) \times gap) / N \rfloor$).
  - Eliminated the middle button overlap bug when toggling edge navigation zones on and off, guaranteeing 100% idempotent layout stability without coordinate drift.
  - Handles nested card controls (e.g. thermostat plus/minus buttons inside container cards), docking them cleanly to the right side of cards with guaranteed spacing.
  - Full-width widgets (`calendar_timeline`, `weather_forecast`, `dynamic_grid`, etc.) and container cards expand and contract smoothly across the usable area ($usableW$).
  - Header text and action icons (Back button, Home icon) dock gracefully to the left and right bounds.
- **Dedicated Toolbar `🔄 Reflow` Action**:
  - Made the `🔄 Reflow` button permanently visible in the editor toolbar, giving users instant one-click dashboard normalization into a clean responsive layout.
  - Toggling `📖 Edge Zones` automatically triggers the responsive reflow across all pages in the configuration.
- **Default Layouts Alignment**:
  - Normalized all default pages in `default_layouts.json` to responsive non-overlapping coordinates.
- **Automated Verification**:
  - Added `test_default_layouts_non_overlapping_tiles` unit test asserting non-overlapping tile geometry and uniform spacing. All 42 unit tests passing.

## 1.5.3 - Apple-Grade Tactile Chyrons, Collision Avoidance & Proportional Edge Reflow

- **Elimination of Canvas Line Slicing & Content Collision Avoidance**:
  - Completely eliminated raw vector stick lines (`d.line`) that cut across user cards and widgets on e-ink screens.
  - Added strict element collision detection in `layout.py`: when elements extend into edge gutters (such as full-width or custom dashboards), edge navigation graphics are suppressed so user cards remain 100% clean and unmolested.
- **Apple Craftsmanship Tactile Capsule Chyrons**:
  - Replaced wireframe chevrons with elegant vertical capsule rails (tactile pills) docked cleanly in clear margin gutters. Rendered with soft Carta grayscale fill (`GRAY_SURFACE`), delicate hairline borders (`GRAY_BORDER`), and crisp centered chevron icons.
  - Upgraded the visual editor (`index.html`) to replace stretched SVG paths with matching tactile capsule guides and clean typography.
- **Hit-Testing Protection & Touch Hierarchy**:
  - Hardened 2D touch hit-testing: taps landing within any element's bounding box (including non-interactive cards, weather widgets, and schedules) are protected from accidental page turns. Edge turn gestures trigger strictly in empty margin gutters.
- **Proportional Horizontal Canvas Adaptation**:
  - Implemented `adaptElementsToEdgeNav` across all pages when toggling edge zones: elements scale and shift proportionally between full-width mode (`[margin, cw - margin]`) and constrained center mode (`[edge_w, cw - edge_w]`) while leaving vertical coordinates, heights, and card orders intact.
  - Refined `reflowPageElements` to respect natural top-to-bottom hierarchy, keeping headers and icons pinned at the top and preserving tile-before-widget flow.
- **Automated Verification**:
  - Added unit tests for tactile capsule rendering, gutter collision avoidance, and touch hit-testing protection. All 41 tests passing.

## 1.5.2 - Security Hardening, Robust Widget Rasterization, Data Sources API & Daemon Resilience

- **Security & Access Control (SEC-01 & SEC-02)**:
  - **Eliminated CSRF State Mutation Vector**: Removed all `GET` routes for `/api/touch` and `/api/devices/{device_id}/touch`. State mutations (toggling lights, calling services, navigating pages) are strictly enforced as `POST` requests, preventing cross-site image trigger vulnerabilities.
  - **Restricted In-Memory Page Simulation**: Restricted `client_page` simulation payloads strictly to Home Assistant Ingress (`is_lan_panel == False`). LAN requests attempting to simulate in-memory page structures are rejected with HTTP 403 Forbidden.
  - **Header-Based Token Authentication**: Enhanced `check_token` to accept standard `Authorization: Bearer <token>` and `X-PaperHub-Token` / `Access-Token` headers in addition to query parameters. Enforced token authentication on LAN SSE event streams (`/api/devices/{device_id}/events`) and device information queries (`/api/devices/{device_id}`).
  - **Device Registration Hard Cap**: Capped total registered device sessions (`MAX_DEVICES = 32`) to prevent memory exhaustion and flash storage wear from unauthorized or random device ID probing.

- **Core Rendering Engine & Widget Fixes (BUG-01, BUG-02, BUG-03, BUG-09, BUG-10)**:
  - **Normalized `draw_card` Box Unpacking**: Extended card container geometry to accept both 4-tuples `(x0, y0, x1, y1)` and 2-point lists `[(x0, y0), (x1, y1)]`. Fixed rendering crashes across 7 major widgets (`dynamic_grid`, `calendar_timeline`, `weather_forecast`, `flight_tracker`, `flight_radar`, `sports_racing`, `sports_match`, and `button`).
  - **Degenerate Geometry Protection**: Protected `draw_card` and `draw_concentric_badge` from zero-area and collapsed bounding boxes when elements fall outside display bounds, preventing Pillow `ValueError` exceptions on smaller displays like TRMNL.
  - **Live State Passing to Tiles & Icons**: Routed resolved template dictionaries `vals.get(i)` directly to all tile drawers (`tile`, `light_tile`, `switch_tile`, `sensor_tile`, `climate_tile`, `media_tile`, `action_tile`) and `icon` elements, ensuring live states, brightness percentages, and dynamic icons render accurately instead of falling back to empty strings.
  - **Jinja Delimiter Restoration**: Enclosed extended data widgets (`flight_tracker`, `flight_radar`, `sports_racing`, `sports_match`) in standard `{{ ... }}` delimiters so Home Assistant evaluates them as live template expressions rather than static strings.
  - **Preserved Custom Grid Item Configuration**: Merged live state updates with configured item definitions in `dynamic_grid`, preserving user-configured icons, actions, and services across live updates.
  - **Defensive Template Binding**: Hardened `last_changed` and `last_updated` expressions in `binding.py` with safe `states[...] is defined` guards, and validated dictionary types before processing replacement rules.

- **Server Stability, Caches & Data Feeds (BUG-04, BUG-05, BUG-07, BUG-08)**:
  - **Defensive Entity Cache Lifecycle**: Reset `_entity_cache` to `{"at": 0.0, "items": []}` rather than `None` on WebSocket state changes, eliminating `TypeError: 'NoneType' object is not subscriptable` regressions.
  - **Live Data Sources API**: Registered `GET /api/sources`, `PUT /api/sources`, and `POST /api/sources/test` endpoints backed by the `feeds` engine, featuring automatic secret masking (`••••••••`) for secure credential management in the web editor.
  - **Panel Setup Compatibility Routes**: Added compatibility handlers for `GET`/`POST /api/panel-setup` and `POST /api/panel-refresh` to prevent 404 alert dialogs in the web UI.
  - **Dynamic WebSocket Connection URL**: Derived the Home Assistant WebSocket URL dynamically from `HA_BASE` and unified authentication token resolution across `HA_TOKEN` and `SUPERVISOR_TOKEN`.
  - **Live Quiet Hours Entity Evaluation**: Evaluated live state from `_entity_cache` when computing next wake intervals for devices configured with quiet hours entity triggers.
  - **Weather Cache Temperature Preservation**: Preserved live current temperature and weather conditions from the latest state fallback when returning cached multi-day forecasts.
  - **Layout Specification Validation**: Enforced strict validation of layout specifications in `PUT /api/layouts`, rejecting invalid payloads where `pages` is missing or not a dictionary.

- **Client Daemon & Evdev Hardening (BUG-06)**:
  - **Eliminated Shell Word Splitting on ETag**: Directly quoted header arguments in `curl` within `paperhub-daemon.sh`, preventing malformed conditional HTTP requests when handling ETags.
  - **Atomic Frame Writes on Touch**: Replaced direct stdout file redirection with atomic temporary files (`${FRAME_TMP}.touch`) on touch events across both `evtest` and raw binary fallback loops, preventing blank screen corruptions if a network blip occurs during a touch fetch.
  - **64-bit Kernel Input Event Support**: Added auto-detection for 32-bit (`IIHHi`, 16-byte) vs 64-bit (`qqHHi`, 24-byte) `struct input_event` packing in `paperhub-evdev.py`, ensuring full compatibility with modern 64-bit Linux kernels (such as on Raspberry Pi and modern e-readers).

- **Automated Verification Suite**:
  - Added 9 new unit tests covering dual bounding box unpacking, widget pixel rasterization, tile value passing, entity cache resilience, template delimiters, header token authentication, LAN simulation blocking, and device registration limits.
  - Expanded test coverage to 39 automated tests, with 100% passing.

## 1.5.1 - Prominent 50% Chevrons, Dynamic Canvas Edge Expansion, Zero-Modal Ingress Presets & Resilient Entities

- **Prominent Edge Navigation Chevrons**:
  - Replaced tiny 44px text glyphs with imposing, Apple-grade geometric chevrons spanning **half the screen tall (50% canvas height)** and **edge-width wide (55%–65% gutter width)**.
  - In Python layout rasterization (`layout.py`), rendered with smooth curved polyline strokes (`T.GRAY_MID`, 8–10px thick) centered within the left and right navigation gutters.
  - In the visual editor (`index.html`), rendered with high-precision vector SVGs (`.edge-chevron-svg`) with dark mode support and tactile hover scaling.
- **Physical Canvas Increase & Decrease on Edge Zones Toggle**:
  - Clicking `📖 Edge Zones` now immediately reflows elements on the page between constrained center mode (`[edge_w, cw - edge_w]`) and full-width mode (`[margin, cw - margin]`).
  - When disabled, tiles, cards, and wide widgets expand horizontally across the entire liberated display width.
  - When enabled, elements cleanly contract to fit within safe gutters.
  - Toggling edge navigation automatically persists to `layouts.json` and notifies devices.
- **Robust Preset Page Creation in Sandboxed Ingress**:
  - Eliminated `window.prompt()` which was blocked inside Home Assistant Ingress iframes.
  - Clicking any preset in the Preset Library automatically generates a clean, unique page slug (e.g. `airspace_radar`, `formula_1`), initializes rotation arrays safely, reflows elements to canvas dimensions, selects the page, and commits via `saveLayouts()`.
  - Introduced an Apple-standard in-DOM dialog modal (`#promptmodal`) with keyboard navigation (Enter/Escape) for custom page creation, duplication, and renaming, completely immune to iframe sandboxing.
- **Resilient Friendly Entities & Token Handling**:
  - Recognized Home Assistant `SUPERVISOR_TOKEN` automatically in addition to `HA_TOKEN`.
  - Added graceful fallback in `api_entities`: if Home Assistant Core or Supervisor times out or experiences a transient error, the endpoint gracefully serves cached entities or offline fixtures with complete friendly names instead of throwing an HTTP 500 error.
  - Added a dedicated `↻ Reload` button in the Entities Explorer header with automatic background retry if entities are initially empty.
  - Added an `Auto` friendly name sync button in Tile properties to instantly sync card titles with the bound Home Assistant entity.
- **Landscape Touch Hit-Testing Accuracy**:
  - Fixed an orientation clamping bug in `_clamp_box` where landscape screens were previously clamped using portrait dimensions, eliminating touch misregistration and preventing false page turns when tapping elements on the right half of rotated screens.
- **Automated Test Suite**:
  - Added 3 new unit tests covering landscape hit-testing accuracy, prominent chevron rendering, and resilient entity fallback (30 total tests, 100% passing).

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

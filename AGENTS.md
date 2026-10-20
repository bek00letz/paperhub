# Notes for Agents: PaperHub

> **Status: stalled (2026-10-20).** Don't start new work here unless the user asks for it. Ideas for e-ink
> dashboards on many screens go to e-paper panel (`bek00letz/epaper-panel`), which supports TRMNL. Why it stalled,
> and what a new approach would need to solve: [docs/FINDINGS-2026-10-20.md](docs/FINDINGS-2026-10-20.md).

Read [ARCHITECTURE.md](ARCHITECTURE.md) and [QUICKSTART.md](QUICKSTART.md) before making structural changes.

---

## 1. Executive Summary & Architecture

PaperHub is an ambient e-ink touch controller system for Home Assistant designed for consumer e-readers (Onyx Boox Go 6, Kindle Paperwhite, Kobo Clara/Libra, and reMarkable).

### The Core Paradigm
- **Server-Side Rasterization**: Home Assistant renders crisp high-DPI bitmaps in ~10–20ms.
- **Client Framebuffer Model**: Client e-readers run a zero-DOM PWA or lightweight Linux daemon that blits frames and transmits touch coordinates `(X, Y)` back to the server.
- **16-Level Grayscale (Carta Depth)**: True 4-bit discrete Carta levels `[0, 17, 34, ... 255]` with subpixel anti-aliasing rather than coarse 1-bit dithering.
- **Server-Side Hit-Testing**: Millisecond-fast 2D hit-testing determines which card or button was tapped, triggers Home Assistant service calls (`toggle`, `turn_on`, `set_temperature`, `navigate_page`), and immediately returns the refreshed bitmap.
- **"Book Metaphor" & Gestures**: Edge taps (left 15% -> previous page, right 15% -> next page) and horizontal swipe gestures enable seamless remote navigation.

---

## 2. Deploying & Testing

The project is structured as a Home Assistant Add-on repository.

```bash
git push origin main
```

In Home Assistant: **Settings → Add-ons → Add-on Store → Repositories → Add Repository** (`https://github.com/bek00letz/paperhub`), then install or rebuild **PaperHub**.

### Local In-Memory Development & Verification

Run the service locally without Home Assistant (falls back to `render/fixture.json`):

```bash
DATA_DIR=/tmp/paperhub-dev FRAME_PORT=8099 INGRESS_PORT=8080 python3 paperhub/addon/app/server.py
```

- Open `http://127.0.0.1:8080/` for the visual WYSIWYG editor.
- Open `http://127.0.0.1:8099/kiosk` for the Universal Kiosk PWA.
- Fetch `http://127.0.0.1:8099/frame.png` for the direct rendered 16-level PNG frame.
- Post touch `curl -X POST http://127.0.0.1:8099/api/touch?x=200&y=300` to test hit-testing.

---

## 3. Endpoints & Ports

| Endpoint | Port | Purpose |
|---|---|---|
| `GET /` | `8080` (Ingress) | WYSIWYG Editor with live preview, device switcher, and touch inspector |
| `GET /kiosk` | `8099` (LAN) / `8080` | Universal Kiosk PWA for Android (Boox/Fully Kiosk) and Web tablets |
| `GET /frame.png` | `8099` (LAN) | Current 16-level grayscale frame for e-reader display |
| `GET /api/devices/{id}/frame.png` | `8099` (LAN) | Device-specific rendered frame |
| `POST /api/devices/{id}/touch` | `8099` (LAN) | Touch coordinate `(X, Y)` and gesture ingestion + hit-testing |
| `GET /api/devices/{id}/events` | `8099` (LAN) | Server-Sent Events (SSE) push stream for instant refresh |
| `GET /api/layouts` / `PUT /api/layouts` | `8080` (Ingress) | Screen layouts configuration JSON |
| `POST /api/preview` | `8080` (Ingress) | On-demand editor canvas rasterizer |

---

## 4. Coding Conventions

- **Coordinates in Canvas Pixels**: All layout coordinates `(x, y, w, h)` match native display profile dimensions (e.g. 1072 × 1448 for Boox Go 6).
- **16-Level Grayscale Palette**: Always render onto an `'L'` mode canvas and quantize using `T.to_16grayscale(img)`. Do NOT hard-threshold to 1-bit unless targeting legacy 1-bit panels.
- **Templates are Batched**: Jinja2 templates are resolved in batch via `resolve_templates()` using delimiter separation (`<<<|paperhub|>>>`), guaranteeing single-request execution.
- **Concentric Geometry**: Every nested container must obey $R_{\text{inner}} = R_{\text{outer}} - \text{padding}$. Never place sharp-cornered children inside rounded containers.
- **Resilient Hit-Testing**: A miss or invalid element action must never throw an unhandled exception or break the frame response.

---

# Apple Craftsmanship & Polish Standard

Any piece of software, interface, component, script, or artifact created in this workspace must look, feel, and function like something Apple shipped.

This is not about superficial aesthetics (it is not just "white backgrounds" or "liquid glass"), but about the uncompromising, obsessive attention to the subtle details that elevate a product from merely functional to undeniably polished, intuitive, and tactile.

## 1. The Core Philosophy
- **Restraint and Intentionality**: Every element, border, gradient, and margin must have a clear reason to exist. If an element doesn't serve the user or clarity, eliminate it. Chrome should recede so content takes center stage.
- **The "Invisible" Polish**: The best design details are the ones the user feels rather than notices—fluid transitions, forgiving touch targets, instantaneous responses, and seamless state preservation.
- **Respect for the Human**: Never confuse, startle, or overwhelm the user. Protect user agency, avoid dark patterns, avoid gratuitous modal interruptions, and respect system preferences (`prefers-color-scheme`, `prefers-reduced-motion`, `prefers-contrast`).

## 2. Visual & Typographic Hierarchy
- **Typography as Architecture**:
  - Use clean, native system font stacks (`-apple-system`, `BlinkMacSystemFont`, `SF Pro Display`, `SF Pro Text`, `system-ui`).
  - Strict typographic scale with intentional line heights (`leading`), letter spacing (`tracking`), and contrast hierarchies (primary, secondary, tertiary labels).
  - Proper typographic punctuation: real quotes (`“ ”`), apostrophes (`’`), em dashes (`—`), and ellipsis (`…`).
- **Concentric Geometry**:
  - Nested corners must be mathematically concentric: $R_{\text{inner}} = R_{\text{outer}} - \text{padding}$. Never have sharp-cornered children inside rounded containers.
  - Standard Apple squircle/continuous corner curves (`corner-smoothing: 60%` / smooth continuous curvature) where supported.
- **Subtle Depth & Elevation**:
  - Soft, multi-layered ambient drop shadows rather than harsh single-offset dark shadows.
  - Delicate hairline borders (e.g., 0.5px or 1px subtle rgba overlays matching dynamic contrast) to define surfaces against any background.
  - Intentional translucent materials only when functional (floating toolbars, overlays, headers), never stacked gratuitously.

## 3. Motion, Physics & Tactility
- **Natural, Organic Spring Physics**:
  - No linear or robotic easing curves. Use mass, stiffness, and damping curves (e.g., Apple-style fluid spring animations: `cubic-bezier(0.25, 1, 0.5, 1)` or fluid springs).
  - Transitions must feel physically grounded—elements expand from their origin, decelerate naturally, and settle with weight.
- **Micro-Interactions & State Polish**:
  - Every interactive surface must respond instantly to touch, hover, and press (subtle scale, luminance shift, or highlight).
  - Zero jarring layout shifts (CLS): reserve space for dynamic content, images, and asynchronous data.
  - Meaningful loading states: use subtle skeleton loaders or gentle shimmering placeholders rather than jarring generic spinners.

## 4. Interaction & Functional Elegance
- **Forgiving & Resilient**:
  - Generous hit targets (minimum 44x44pt on touch, comfortable click zones on pointer).
  - Inline validation that is helpful and constructive, not punitive.
  - Preserve user inputs and state across navigation or transient network blips.
- **Sensible, Thoughtful Defaults**:
  - Pre-configure the most likely, safest, and highest-quality default choice.
  - Confirmation required only for truly destructive, irreversible actions—make reversible actions easy to undo instead.
- **Zero "Sludge" & Cognitive Clutter**:
  - Eliminate redundant badges, unnecessary tooltips, cluttering icons, and marketing popovers.
  - Clear, concise, active human copy. Avoid jargon, robotic messages, or ambiguous button labels (e.g. use "Delete Note" instead of "OK").

## 5. Artifacts, Code & Output Standards
- **Artifacts**: Clean, scannable, well-typeset Markdown with elegant tables, clear visual callouts, structured sections, and zero boilerplate filler.
- **Code & CLI Tools**: Clean terminal formatting, clear progress indicators, graceful failure exits, helpful error messages with actionable remedy hints, and polished CLI help menus.

## 6. Project Scaffolding & AGENTS.md Generation
- **Mandatory Default**: Whenever asked to craft, initialize, or update an `AGENTS.md` (or `.agents/rules/*.md`) file for any project or repository, **always include this Apple Craftsmanship & Polish Standard** as a foundational, default rule section so the project maintains this bar self-containedly.

# Changelog

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
